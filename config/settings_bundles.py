"""Bundle aggregates built from flat :class:`~config.settings.Settings` fields."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .admin_optimization_settings import AdminOptimizationSettings
from .bot_settings import BotSettings
from .messaging_settings import MessagingSettings
from .model_routing_settings import ModelRoutingSettings
from .observability_settings import ObservabilitySettings
from .server_runtime_settings import ProviderThroughputSettings, ServerRuntimeSettings
from .web_fetch_settings import WebFetchSettings

if TYPE_CHECKING:
    from .settings import Settings


def build_web_fetch_bundle(settings: Settings) -> WebFetchSettings:
    return WebFetchSettings(
        enable_web_server_tools=settings.enable_web_server_tools,
        web_fetch_allowed_schemes=settings.web_fetch_allowed_schemes,
        web_fetch_allow_private_networks=settings.web_fetch_allow_private_networks,
    )


def build_observability_bundle(settings: Settings) -> ObservabilitySettings:
    return ObservabilitySettings(
        log_raw_api_payloads=settings.log_raw_api_payloads,
        log_raw_sse_events=settings.log_raw_sse_events,
        log_api_error_tracebacks=settings.log_api_error_tracebacks,
        log_raw_messaging_content=settings.log_raw_messaging_content,
        log_raw_cli_diagnostics=settings.log_raw_cli_diagnostics,
        log_messaging_error_details=settings.log_messaging_error_details,
        debug_platform_edits=settings.debug_platform_edits,
        debug_subagent_stack=settings.debug_subagent_stack,
        structured_trace_sink=settings.structured_trace_sink,
    )


def build_model_routing_bundle(settings: Settings) -> ModelRoutingSettings:
    return ModelRoutingSettings(
        model=settings.model,
        model_opus=settings.model_opus,
        model_sonnet=settings.model_sonnet,
        model_haiku=settings.model_haiku,
        enable_model_thinking=settings.enable_model_thinking,
        enable_opus_thinking=settings.enable_opus_thinking,
        enable_sonnet_thinking=settings.enable_sonnet_thinking,
        enable_haiku_thinking=settings.enable_haiku_thinking,
    )


def build_bot_bundle(settings: Settings) -> BotSettings:
    return BotSettings(
        telegram_bot_token=settings.telegram_bot_token,
        allowed_telegram_user_id=settings.allowed_telegram_user_id,
        discord_bot_token=settings.discord_bot_token,
        allowed_discord_channels=settings.allowed_discord_channels,
        allowed_dir=settings.allowed_dir,
        max_message_log_entries_per_chat=settings.max_message_log_entries_per_chat,
        voice_note_enabled=settings.voice_note_enabled,
        whisper_device=settings.whisper_device,
        whisper_model=settings.whisper_model,
        hf_token=settings.hf_token,
    )


def build_admin_optimization_bundle(settings: Settings) -> AdminOptimizationSettings:
    return AdminOptimizationSettings(
        fast_prefix_detection=settings.fast_prefix_detection,
        enable_network_probe_mock=settings.enable_network_probe_mock,
        enable_title_generation_skip=settings.enable_title_generation_skip,
        enable_suggestion_mode_skip=settings.enable_suggestion_mode_skip,
        enable_filepath_extraction_mock=settings.enable_filepath_extraction_mock,
    )


def build_messaging_bundle(settings: Settings) -> MessagingSettings:
    return MessagingSettings(
        messaging_platform=settings.messaging_platform,
        messaging_rate_limit=settings.messaging_rate_limit,
        messaging_rate_window=settings.messaging_rate_window,
        log_messaging_error_details=settings.log_messaging_error_details,
        log_raw_messaging_content=settings.log_raw_messaging_content,
    )


def build_server_runtime_bundle(settings: Settings) -> ServerRuntimeSettings:
    return ServerRuntimeSettings(
        host=settings.host,
        port=settings.port,
        anthropic_auth_token=settings.anthropic_auth_token,
    )


def build_provider_throughput_bundle(settings: Settings) -> ProviderThroughputSettings:
    return ProviderThroughputSettings(
        provider_rate_limit=settings.provider_rate_limit,
        provider_rate_window=settings.provider_rate_window,
        provider_max_concurrency=settings.provider_max_concurrency,
    )
