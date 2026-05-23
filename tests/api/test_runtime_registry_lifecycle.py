"""Lifecycle tests for ``AppRuntime`` ↔ ``app.state.provider_registry`` coupling."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from config.settings import Settings
from providers.registry import ProviderRegistry

_RUNTIME_EXTRAS = {
    "voice_note_enabled": True,
    "whisper_model": "base",
    "whisper_device": "cpu",
    "hf_token": "",
    "nvidia_nim_api_key": "",
    "claude_cli_bin": "claude",
    "uses_process_anthropic_auth_token": lambda: False,
    "messaging_rate_limit": 1,
    "messaging_rate_window": 1.0,
    "max_message_log_entries_per_chat": None,
    "debug_platform_edits": False,
    "debug_subagent_stack": False,
    "log_api_error_tracebacks": False,
    "log_raw_messaging_content": False,
    "log_raw_cli_diagnostics": False,
    "log_messaging_error_details": False,
    "configured_chat_model_refs": lambda: (),
    "structured_trace_sink": "default",
}


def _app_settings(**kwargs):
    """Minimal ``Settings`` surface for ``AppRuntime`` lifecycle tests."""
    data = {**_RUNTIME_EXTRAS, **kwargs}
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_shutdown_cleanup_prefers_app_state_provider_registry(tmp_path):
    """When state and ``_provider_registry`` diverge, shutdown cleans ``app.state``."""
    from messaging.limiter import MessagingRateLimiter

    await MessagingRateLimiter.shutdown_instance(timeout=0.1)

    api_runtime_mod = importlib.import_module("api.runtime")
    settings = cast(
        Settings,
        _app_settings(
            messaging_platform="none",
            telegram_bot_token=None,
            allowed_telegram_user_id=None,
            discord_bot_token=None,
            allowed_discord_channels=None,
            allowed_dir=str(tmp_path / "workspace"),
            claude_workspace=str(tmp_path / "data"),
            host="127.0.0.1",
            port=8082,
        ),
    )
    app = FastAPI()
    runtime = api_runtime_mod.AppRuntime(app=app, settings=settings)
    stale = ProviderRegistry()
    fresh = ProviderRegistry()
    runtime._provider_registry = stale
    app.state.provider_registry = fresh

    async def limiter_shutdown(*_args: object, **_kwargs: object) -> None:
        return None

    stale_cleanup = AsyncMock()
    fresh_cleanup = AsyncMock()
    with (
        patch.object(stale, "cleanup", stale_cleanup),
        patch.object(fresh, "cleanup", fresh_cleanup),
        patch(
            "messaging.limiter.MessagingRateLimiter.shutdown_instance",
            new=classmethod(limiter_shutdown),
        ),
    ):
        await runtime.shutdown()

    fresh_cleanup.assert_awaited_once()
    stale_cleanup.assert_not_awaited()


@pytest.mark.asyncio
async def test_startup_installs_claude_proxy_runtime_after_success(tmp_path):
    from messaging.limiter import MessagingRateLimiter

    await MessagingRateLimiter.shutdown_instance(timeout=0.1)

    api_runtime_mod = importlib.import_module("api.runtime")
    settings = cast(
        Settings,
        _app_settings(
            messaging_platform="none",
            telegram_bot_token=None,
            allowed_telegram_user_id=None,
            discord_bot_token=None,
            allowed_discord_channels=None,
            allowed_dir=str(tmp_path / "workspace"),
            claude_workspace=str(tmp_path / "data"),
            host="127.0.0.1",
            port=9099,
        ),
    )
    runtime = api_runtime_mod.AppRuntime(app=FastAPI(), settings=settings)
    with (
        patch.object(api_runtime_mod.logging, "getLogger", return_value=MagicMock()),
        patch.object(api_runtime_mod.logger, "info"),
        patch.object(ProviderRegistry, "validate_configured_models", new=AsyncMock()),
        patch.object(ProviderRegistry, "start_model_list_refresh"),
        patch.object(ProviderRegistry, "cleanup", new=AsyncMock()),
        patch(
            "messaging.bootstrap.create_messaging_platform",
            return_value=None,
        ),
    ):
        await runtime.startup()

    assert getattr(runtime.app.state, "claude_proxy_runtime", None) is runtime
    await runtime.shutdown()


@pytest.mark.asyncio
async def test_replace_provider_registry_updates_runtime_field_and_app_state(tmp_path):
    api_runtime_mod = importlib.import_module("api.runtime")
    settings = cast(
        Settings,
        _app_settings(
            messaging_platform="none",
            telegram_bot_token=None,
            allowed_telegram_user_id=None,
            discord_bot_token=None,
            allowed_discord_channels=None,
            allowed_dir=str(tmp_path / "workspace"),
            claude_workspace=str(tmp_path / "data"),
            host="127.0.0.1",
            port=9098,
        ),
    )
    app = FastAPI()
    runtime = api_runtime_mod.AppRuntime(app=app, settings=settings)
    runtime._provider_registry = ProviderRegistry()
    app.state.provider_registry = runtime._provider_registry
    new_registry = ProviderRegistry()

    with patch.object(
        ProviderRegistry,
        "start_model_list_refresh",
        MagicMock(),
    ) as warm:
        runtime.replace_provider_registry(new_registry, settings=settings)

    assert runtime._provider_registry is new_registry
    assert app.state.provider_registry is new_registry
    warm.assert_called_once_with(settings)
