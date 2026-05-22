"""Per-node Claude CLI turn pipeline (extracted from :class:`ClaudeMessageHandler`)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from loguru import logger

from core.anthropic import format_user_error_preview, get_user_facing_error_message
from core.trace import trace_event

from .event_parser import parse_cli_event
from .models import IncomingMessage
from .node_event_pipeline import handle_session_info_event, process_parsed_cli_event
from .platforms.base import MessagingPlatform, SessionManagerInterface
from .safe_diagnostics import format_exception_for_log
from .session import SessionStore
from .transcript import RenderCtx, ThrottledTranscriptEditor, TranscriptBuffer
from .trees.queue_manager import (
    MessageNode,
    MessageState,
    TreeQueueManager,
)


@dataclass(frozen=True, slots=True)
class ClaudeNodeProcessingContext:
    """Narrow façade of handler state consumed by :class:`ClaudeNodeProcessor`."""

    platform: MessagingPlatform
    cli_manager: SessionManagerInterface
    session_store: SessionStore
    tree_queue_fn: Callable[[], TreeQueueManager]
    debug_platform_edits: bool
    debug_subagent_stack: bool
    log_raw_cli_diagnostics: bool
    log_messaging_error_details: bool
    format_status: Callable[..., str]
    parse_mode: Callable[[], str | None]
    get_render_ctx: Callable[[], RenderCtx]
    get_limit_chars: Callable[[], int]


class ClaudeNodeProcessor:
    """Orchestrate one CLI session + transcript updates for a single tree node."""

    def __init__(self, ctx: ClaudeNodeProcessingContext) -> None:
        self._ctx = ctx

    def _create_transcript_and_render_ctx(self) -> tuple[TranscriptBuffer, RenderCtx]:
        transcript = TranscriptBuffer(
            show_tool_results=False,
            debug_subagent_stack=self._ctx.debug_subagent_stack,
        )
        return transcript, self._ctx.get_render_ctx()

    async def _propagate_error_to_children(
        self,
        node_id: str,
        error_msg: str,
        child_status_text: str,
    ) -> None:
        tree_queue = self._ctx.tree_queue_fn()
        affected = await tree_queue.mark_node_error(
            node_id, error_msg, propagate_to_children=True
        )
        ctx = self._ctx
        for child in affected[1:]:
            ctx.platform.fire_and_forget(
                ctx.platform.queue_edit_message(
                    child.incoming.chat_id,
                    child.status_message_id,
                    ctx.format_status("❌", "Cancelled:", child_status_text),
                    parse_mode=ctx.parse_mode(),
                )
            )

    async def process_node(self, node_id: str, node: MessageNode) -> None:
        """CLI task entry used by :class:`~messaging.trees.manager.TreeQueueManager`."""
        incoming = node.incoming
        status_msg_id = node.status_message_id
        chat_id = incoming.chat_id

        with logger.contextualize(node_id=node_id, chat_id=chat_id):
            await self._process_node_impl(
                node_id, node, chat_id, status_msg_id, incoming
            )

    async def _process_node_impl(
        self,
        node_id: str,
        node: MessageNode,
        chat_id: str,
        status_msg_id: str,
        incoming: IncomingMessage,
    ) -> None:
        ctx = self._ctx
        tree_queue = ctx.tree_queue_fn()

        tree = tree_queue.get_tree_for_node(node_id)
        if tree:
            await tree.update_state(node_id, MessageState.IN_PROGRESS)

        transcript, render_ctx = self._create_transcript_and_render_ctx()

        had_transcript_events = False
        captured_session_id = None
        temp_session_id = None
        last_status: str | None = None

        parent_session_id = None
        platform_nm = getattr(ctx.platform, "name", "messaging")
        if tree and node.parent_id:
            parent_session_id = tree.get_parent_session_id(node_id)
            if parent_session_id:
                trace_event(
                    stage="claude_cli",
                    event="claude_cli.fork.from_parent_session",
                    source=platform_nm,
                    chat_id=chat_id,
                    node_id=node_id,
                    parent_session_id=parent_session_id,
                )

        editor = ThrottledTranscriptEditor(
            platform=ctx.platform,
            parse_mode=ctx.parse_mode(),
            get_limit_chars=ctx.get_limit_chars,
            transcript=transcript,
            render_ctx=render_ctx,
            node_id=node_id,
            chat_id=chat_id,
            status_msg_id=status_msg_id,
            debug_platform_edits=ctx.debug_platform_edits,
            log_messaging_error_details=ctx.log_messaging_error_details,
        )

        async def update_ui(status: str | None = None, force: bool = False) -> None:
            await editor.update(status, force=force)

        async def propagate_cb(nid: str, err: str, label: str) -> None:
            await self._propagate_error_to_children(nid, err, label)

        try:
            try:
                (
                    cli_session,
                    session_or_temp_id,
                    is_new,
                ) = await ctx.cli_manager.get_or_create_session(
                    session_id=parent_session_id
                )
                if is_new:
                    temp_session_id = session_or_temp_id
                else:
                    captured_session_id = session_or_temp_id

                sess_evt = (
                    "claude_cli.session.pending_created"
                    if is_new
                    else "claude_cli.session.reused"
                )
                trace_event(
                    stage="claude_cli",
                    event=sess_evt,
                    source=platform_nm,
                    chat_id=chat_id,
                    node_id=node_id,
                    status_message_id=status_msg_id,
                    session_handle=str(session_or_temp_id),
                    parent_resume_session_id=parent_session_id,
                    fork_requested=bool(parent_session_id),
                )
                trace_event(
                    stage="claude_cli",
                    event="claude_cli.request.sent",
                    source=platform_nm,
                    chat_id=chat_id,
                    node_id=node_id,
                    prompt=incoming.text,
                    fork_session_arg=bool(parent_session_id),
                    resume_session_arg=parent_session_id,
                )
            except RuntimeError as e:
                error_message = get_user_facing_error_message(e)
                transcript.apply({"type": "error", "message": error_message})
                await update_ui(
                    ctx.format_status("⏳", "Session limit reached"),
                    force=True,
                )
                if tree:
                    await tree.update_state(
                        node_id,
                        MessageState.ERROR,
                        error_message=error_message,
                    )
                trace_event(
                    stage="claude_cli",
                    event="claude_cli.session.limit_reached",
                    source=platform_nm,
                    chat_id=chat_id,
                    node_id=node_id,
                )
                return

            async for event_data in cli_session.start_task(
                incoming.text,
                session_id=parent_session_id,
                fork_session=bool(parent_session_id),
            ):
                if not isinstance(event_data, dict):
                    logger.warning(
                        f"HANDLER: Non-dict event received: {type(event_data)}"
                    )
                    continue

                (
                    captured_session_id,
                    temp_session_id,
                ) = await handle_session_info_event(
                    event_data,
                    tree,
                    node_id,
                    captured_session_id,
                    temp_session_id,
                    cli_manager=ctx.cli_manager,
                    session_store=ctx.session_store,
                )
                if event_data.get("type") == "session_info":
                    continue

                parsed_list = parse_cli_event(
                    event_data, log_raw_cli=ctx.log_raw_cli_diagnostics
                )

                for parsed in parsed_list:
                    (
                        last_status,
                        had_transcript_events,
                    ) = await process_parsed_cli_event(
                        parsed,
                        transcript,
                        update_ui,
                        last_status,
                        had_transcript_events,
                        tree,
                        node_id,
                        captured_session_id,
                        session_store=ctx.session_store,
                        format_status=ctx.format_status,
                        propagate_error_to_children=propagate_cb,
                        log_messaging_error_details=ctx.log_messaging_error_details,
                    )

        except asyncio.CancelledError:
            trace_event(
                stage="claude_cli",
                event="turn.processor.cancelled",
                source=platform_nm,
                chat_id=chat_id,
                node_id=node_id,
            )
            logger.warning(f"HANDLER: Task cancelled for node {node_id}")
            cancel_reason = None
            if isinstance(node.context, dict):
                cancel_reason = node.context.get("cancel_reason")

            if cancel_reason == "stop":
                await update_ui(ctx.format_status("⏹", "Stopped."), force=True)
            else:
                transcript.apply({"type": "error", "message": "Task was cancelled"})
                await update_ui(ctx.format_status("❌", "Cancelled"), force=True)

            if tree:
                await tree.update_state(
                    node_id, MessageState.ERROR, error_message="Cancelled by user"
                )
        except Exception as e:
            trace_event(
                stage="claude_cli",
                event="turn.processor.exception",
                source=platform_nm,
                chat_id=chat_id,
                node_id=node_id,
                exc_type=type(e).__name__,
            )
            logger.error(
                "HANDLER: Task failed with exception: {}",
                format_exception_for_log(
                    e, log_full_message=ctx.log_messaging_error_details
                ),
            )
            error_msg = format_user_error_preview(e)
            transcript.apply({"type": "error", "message": error_msg})
            await update_ui(ctx.format_status("💥", "Task Failed"), force=True)
            if tree:
                await self._propagate_error_to_children(
                    node_id,
                    error_msg,
                    "Parent task failed",
                )
        finally:
            trace_event(
                stage="routing",
                event="turn.processor.finished",
                source=platform_nm,
                chat_id=chat_id,
                node_id=node_id,
                claude_session_id=captured_session_id or temp_session_id,
            )
            try:
                if captured_session_id:
                    await ctx.cli_manager.remove_session(captured_session_id)
                elif temp_session_id:
                    await ctx.cli_manager.remove_session(temp_session_id)
            except Exception as e:
                logger.debug(
                    "Failed to remove session for node {}: {}",
                    node_id,
                    format_exception_for_log(
                        e, log_full_message=ctx.log_messaging_error_details
                    ),
                )
