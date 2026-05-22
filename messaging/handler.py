"""
Claude Message Handler

Platform-agnostic Claude interaction logic.
Handles the core workflow of processing user messages via Claude CLI.
Uses tree-based queuing for message ordering.
"""

from loguru import logger

from core.trace import trace_event

from .claude_node_processor import ClaudeNodeProcessingContext, ClaudeNodeProcessor
from .handler_queue_ux import (
    initial_status_message,
    mark_processing_status,
    refresh_queued_positions,
)
from .incoming_turn import dispatch_incoming_user_message
from .models import IncomingMessage
from .platforms.base import MessagingPlatform, SessionManagerInterface
from .rendering.profiles import build_rendering_profile
from .safe_diagnostics import format_exception_for_log
from .session import SessionStore
from .transcript import RenderCtx
from .trees.queue_manager import (
    MessageNode,
    MessageState,
    MessageTree,
    TreeQueueManager,
)


class ClaudeMessageHandler:
    """
    Platform-agnostic handler for Claude interactions.

    Uses a tree-based message queue where:
    - New messages create a tree root
    - Replies become children of the message being replied to
    - Each node has state: PENDING, IN_PROGRESS, COMPLETED, ERROR
    - Per-tree queue ensures ordered processing
    """

    def __init__(
        self,
        platform: MessagingPlatform,
        cli_manager: SessionManagerInterface,
        session_store: SessionStore,
        *,
        debug_platform_edits: bool = False,
        debug_subagent_stack: bool = False,
        log_raw_messaging_content: bool = False,
        log_raw_cli_diagnostics: bool = False,
        log_messaging_error_details: bool = False,
    ):
        self.platform = platform
        self.cli_manager = cli_manager
        self.session_store = session_store
        self._debug_platform_edits = debug_platform_edits
        self._debug_subagent_stack = debug_subagent_stack
        self._log_raw_messaging_content = log_raw_messaging_content
        self._log_raw_cli_diagnostics = log_raw_cli_diagnostics
        self._log_messaging_error_details = log_messaging_error_details

        self._rendering_profile = build_rendering_profile(platform.name)

        self._tree_queue = TreeQueueManager(
            queue_update_callback=self.update_queue_positions,
            node_started_callback=self.mark_node_processing,
            log_messaging_error_details=log_messaging_error_details,
        )
        self._node_processor_ctx = ClaudeNodeProcessingContext(
            platform=self.platform,
            cli_manager=self.cli_manager,
            session_store=self.session_store,
            tree_queue_fn=lambda: self._tree_queue,
            debug_platform_edits=self._debug_platform_edits,
            debug_subagent_stack=self._debug_subagent_stack,
            log_raw_cli_diagnostics=self._log_raw_cli_diagnostics,
            log_messaging_error_details=self._log_messaging_error_details,
            format_status=self.format_status,
            parse_mode=self._parse_mode,
            get_render_ctx=self.get_render_ctx,
            get_limit_chars=self._get_limit_chars,
        )
        self._node_processor = ClaudeNodeProcessor(self._node_processor_ctx)

    def format_status(self, emoji: str, label: str, suffix: str | None = None) -> str:
        return self._rendering_profile.format_status(emoji, label, suffix)

    def _parse_mode(self) -> str | None:
        return self._rendering_profile.parse_mode

    def get_render_ctx(self) -> RenderCtx:
        return self._rendering_profile.render_ctx

    def _get_limit_chars(self) -> int:
        return self._rendering_profile.limit_chars

    @property
    def tree_queue(self) -> TreeQueueManager:
        """Accessor for the current tree queue manager."""
        return self._tree_queue

    def replace_tree_queue(self, tree_queue: TreeQueueManager) -> None:
        """Replace tree queue manager via explicit API."""
        self._tree_queue = tree_queue
        self._tree_queue.set_queue_update_callback(self.update_queue_positions)
        self._tree_queue.set_node_started_callback(self.mark_node_processing)

    async def handle_message(self, incoming: IncomingMessage) -> None:
        """
        Main entry point for handling an incoming message.

        Determines if this is a new conversation or reply,
        creates/extends the message tree, and queues for processing.
        """
        platform_name = getattr(self.platform, "name", "messaging")
        trace_event(
            stage="ingress",
            event="turn.received",
            source=platform_name,
            chat_id=incoming.chat_id,
            platform_message_id=incoming.message_id,
            reply_to_message_id=incoming.reply_to_message_id,
            thread_id=getattr(incoming, "message_thread_id", None),
            message_text=incoming.text or "",
        )

        with logger.contextualize(
            chat_id=incoming.chat_id, node_id=incoming.message_id
        ):
            await self._handle_message_impl(incoming)

    async def _handle_message_impl(self, incoming: IncomingMessage) -> None:
        """Test seam and hook for turn handling (dispatches to shared ingress logic)."""
        await dispatch_incoming_user_message(self, incoming)

    async def update_queue_positions(self, tree: MessageTree) -> None:
        """Refresh queued status messages after a dequeue."""
        await refresh_queued_positions(self, tree)

    async def mark_node_processing(self, tree: MessageTree, node_id: str) -> None:
        """Update the dequeued node's status to processing immediately."""
        await mark_processing_status(self, tree, node_id)

    async def _process_node(
        self,
        node_id: str,
        node: MessageNode,
    ) -> None:
        """Core task processor - handles a single Claude CLI interaction."""
        await self._node_processor.process_node(node_id, node)

    def _get_initial_status(
        self,
        tree: object | None,
        parent_node_id: str | None,
    ) -> str:
        """Get initial status message text."""
        return initial_status_message(self, tree, parent_node_id)

    async def stop_all_tasks(self) -> int:
        """
        Stop all pending and in-progress tasks.

        Order of operations:
        1. Cancel tree queue tasks (uses internal locking)
        2. Stop CLI sessions
        3. Update UI for all affected nodes
        """
        # 1. Cancel tree queue tasks using the public async method
        logger.info("Cancelling tree queue tasks...")
        cancelled_nodes = await self.tree_queue.cancel_all()
        logger.info(f"Cancelled {len(cancelled_nodes)} nodes")

        # 2. Stop CLI sessions - this kills subprocesses and ensures everything is dead
        logger.info("Stopping all CLI sessions...")
        await self.cli_manager.stop_all()

        # 3. Update UI and persist state for all cancelled nodes
        self.update_cancelled_nodes_ui(cancelled_nodes)

        return len(cancelled_nodes)

    async def stop_task(self, node_id: str) -> int:
        """
        Stop a single queued or in-progress task node.

        Used when the user replies "/stop" to a specific status/user message.
        """
        tree = self.tree_queue.get_tree_for_node(node_id)
        if tree:
            node = tree.get_node(node_id)
            if node and node.state not in (MessageState.COMPLETED, MessageState.ERROR):
                # Used by _process_node cancellation path to render "Stopped."
                node.set_context({"cancel_reason": "stop"})

        cancelled_nodes = await self.tree_queue.cancel_node(node_id)
        self.update_cancelled_nodes_ui(cancelled_nodes)
        return len(cancelled_nodes)

    def record_outgoing_message(
        self,
        platform: str,
        chat_id: str,
        msg_id: str | None,
        kind: str,
    ) -> None:
        """Record outgoing message ID for /clear. Best-effort, never raises."""
        if not msg_id:
            return
        try:
            self.session_store.record_message_id(
                platform, chat_id, str(msg_id), direction="out", kind=kind
            )
        except Exception as e:
            logger.debug(
                "Failed to record message_id: {}",
                format_exception_for_log(
                    e, log_full_message=self._log_messaging_error_details
                ),
            )

    def update_cancelled_nodes_ui(self, nodes: list[MessageNode]) -> None:
        """Update status messages and persist tree state for cancelled nodes."""
        trees_to_save: dict[str, MessageTree] = {}
        for node in nodes:
            self.platform.fire_and_forget(
                self.platform.queue_edit_message(
                    node.incoming.chat_id,
                    node.status_message_id,
                    self.format_status("⏹", "Stopped."),
                    parse_mode=self._parse_mode(),
                )
            )
            tree = self.tree_queue.get_tree_for_node(node.node_id)
            if tree:
                trees_to_save[tree.root_id] = tree
        for root_id, tree in trees_to_save.items():
            self.session_store.save_tree(root_id, tree.to_dict())
