"""Optional messaging platform bootstrap (CLI wiring stays under ``api``).

``messaging`` must not import ``cli`` (:mod:`tests.contracts.test_import_boundaries`);
this module maps :class:`~config.settings.Settings` to platform knobs and restores
conversation trees independent of Claude CLI orchestration.
"""

from typing import TYPE_CHECKING

from loguru import logger

from config.settings import Settings
from messaging.handler import ClaudeMessageHandler
from messaging.platforms.factory import (
    MessagingPlatformOptions,
    create_messaging_platform,
)
from messaging.session import SessionStore
from messaging.trees.queue_manager import TreeQueueManager
from messaging.voice_backend import TranscriptionBackend

if TYPE_CHECKING:
    from messaging.platforms.base import MessagingPlatform


def build_messaging_platform_options(
    settings: Settings, *, nim_transcription_backend: TranscriptionBackend
) -> MessagingPlatformOptions:
    """Map :class:`~config.settings.Settings` into platform factory knobs."""
    return MessagingPlatformOptions(
        telegram_bot_token=settings.telegram_bot_token,
        allowed_telegram_user_id=settings.allowed_telegram_user_id,
        discord_bot_token=settings.discord_bot_token,
        allowed_discord_channels=settings.allowed_discord_channels,
        voice_note_enabled=settings.voice_note_enabled,
        whisper_model=settings.whisper_model,
        whisper_device=settings.whisper_device,
        hf_token=settings.hf_token,
        nvidia_nim_api_key=settings.nvidia_nim_api_key,
        nim_transcription_backend=nim_transcription_backend,
        messaging_rate_limit=settings.messaging_rate_limit,
        messaging_rate_window=settings.messaging_rate_window,
        log_raw_messaging_content=settings.log_raw_messaging_content,
        log_api_error_tracebacks=settings.log_api_error_tracebacks,
        log_messaging_error_details=settings.log_messaging_error_details,
    )


def create_optional_messaging_platform(
    settings: Settings, *, nim_transcription_backend: TranscriptionBackend
) -> MessagingPlatform | None:
    """Return Telegram/Discord platform when configured (not started yet)."""
    return create_messaging_platform(
        settings.messaging_platform,
        build_messaging_platform_options(
            settings, nim_transcription_backend=nim_transcription_backend
        ),
    )


def restore_tree_queue_state(
    settings: Settings, handler: ClaudeMessageHandler, session_store: SessionStore
) -> None:
    """Hydrate persisted trees after constructing the handler."""
    saved_trees = session_store.get_all_trees()
    if not saved_trees:
        return

    logger.info("Restoring {} conversation trees...", len(saved_trees))
    handler.replace_tree_queue(
        TreeQueueManager.from_dict(
            {
                "trees": saved_trees,
                "node_to_tree": session_store.get_node_mapping(),
            },
            queue_update_callback=handler.update_queue_positions,
            node_started_callback=handler.mark_node_processing,
            log_messaging_error_details=settings.log_messaging_error_details,
        )
    )
    if handler.tree_queue.cleanup_stale_nodes() > 0:
        tree_data = handler.tree_queue.to_dict()
        session_store.sync_from_tree_data(tree_data["trees"], tree_data["node_to_tree"])
