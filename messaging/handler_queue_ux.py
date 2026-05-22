"""Queue and status UX collaborators for :class:`~messaging.handler.ClaudeMessageHandler`."""

from __future__ import annotations

from typing import Any

from loguru import logger

from .safe_diagnostics import format_exception_for_log
from .trees.queue_manager import MessageState, MessageTree


async def refresh_queued_positions(handler: Any, tree: MessageTree) -> None:
    """Refresh queued status messages after a dequeue (``TreeQueueManager`` callback)."""
    try:
        queued_ids = await tree.get_queue_snapshot()
    except Exception as e:
        logger.warning(
            "Failed to read queue snapshot: {}",
            format_exception_for_log(
                e, log_full_message=handler._log_messaging_error_details
            ),
        )
        return

    if not queued_ids:
        return

    position = 0
    for node_id in queued_ids:
        node = tree.get_node(node_id)
        if not node or node.state != MessageState.PENDING:
            continue
        position += 1
        handler.platform.fire_and_forget(
            handler.platform.queue_edit_message(
                node.incoming.chat_id,
                node.status_message_id,
                handler.format_status(
                    "📋", "Queued", f"(position {position}) - waiting..."
                ),
                parse_mode=handler._parse_mode(),
            )
        )


async def mark_processing_status(handler: Any, tree: MessageTree, node_id: str) -> None:
    """Bump the dequeued node's status message to Processing."""
    node = tree.get_node(node_id)
    if not node or node.state == MessageState.ERROR:
        return
    handler.platform.fire_and_forget(
        handler.platform.queue_edit_message(
            node.incoming.chat_id,
            node.status_message_id,
            handler.format_status("🔄", "Processing..."),
            parse_mode=handler._parse_mode(),
        )
    )


def initial_status_message(
    handler: Any,
    tree: object | None,
    parent_node_id: str | None,
) -> str:
    """Return the editable status prefix for a newly accepted user turn."""
    if tree and parent_node_id:
        if handler.tree_queue.is_node_tree_busy(parent_node_id):
            queue_size = handler.tree_queue.get_queue_size(parent_node_id) + 1
            return handler.format_status(
                "📋", "Queued", f"(position {queue_size}) - waiting..."
            )
        return handler.format_status("🔄", "Continuing conversation...")

    return handler.format_status("⏳", "Launching new Claude CLI instance...")
