"""Application runtime composition and lifecycle ownership."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import FastAPI
from loguru import logger

from api.admin_urls import local_admin_url
from api.runtime_lifecycle import (
    best_effort,
    log_startup_failure,
    startup_failure_message,
    warn_if_process_auth_token,
)
from api.trace_sink import (
    apply_structured_trace_settings,
    reset_structured_trace_settings,
)
from config.settings import Settings, get_settings
from providers.exceptions import ServiceUnavailableError
from providers.registry import ProviderRegistry

if TYPE_CHECKING:
    from cli.manager import CLISessionManager
    from messaging.handler import ClaudeMessageHandler
    from messaging.platforms.base import MessagingPlatform


__all__ = (
    "AppRuntime",
    "best_effort",
    "log_startup_failure",
    "startup_failure_message",
    "warn_if_process_auth_token",
)


@dataclass(slots=True)
class AppRuntime:
    """Own optional messaging, CLI, session, and provider runtime resources."""

    app: FastAPI
    settings: Settings
    _provider_registry: ProviderRegistry | None = field(default=None, init=False)
    messaging_platform: MessagingPlatform | None = None
    message_handler: ClaudeMessageHandler | None = None
    cli_manager: CLISessionManager | None = None

    @classmethod
    def for_app(
        cls,
        app: FastAPI,
        settings: Settings | None = None,
    ) -> AppRuntime:
        return cls(app=app, settings=settings or get_settings())

    async def startup(self) -> None:
        logger.info("Starting Claude Code Proxy...")
        admin_url = local_admin_url(self.settings)
        self._provider_registry = ProviderRegistry()
        self.app.state.provider_registry = self._provider_registry
        try:
            apply_structured_trace_settings(self.settings)
            warn_if_process_auth_token(self.settings)
            await self._validate_configured_models_best_effort()
            self._provider_registry.start_model_list_refresh(self.settings)
            await self._start_messaging_if_configured()
            self._publish_state()
            self.app.state.claude_proxy_runtime = self
            logging.getLogger("uvicorn.error").info(
                "Admin UI: %s (local-only)", admin_url
            )
        except Exception as exc:
            log_startup_failure(self.settings, exc)
            await best_effort(
                "provider_registry.cleanup",
                self._provider_registry.cleanup(),
                log_verbose_errors=self.settings.log_api_error_tracebacks,
            )
            raise

    async def _validate_configured_models_best_effort(self) -> None:
        """Warm validation status without blocking first-run/admin access."""
        if self._provider_registry is None:
            return
        try:
            await self._provider_registry.validate_configured_models(self.settings)
        except ServiceUnavailableError as exc:
            self.app.state.startup_validation_error = exc.message
            logger.warning(
                "Configured provider model validation failed during startup; "
                "server will continue and requests will fail at provider resolution "
                "when config is incomplete. {}",
                exc.message,
            )

    def replace_provider_registry(
        self, registry: ProviderRegistry, *, settings: Settings
    ) -> None:
        """Install ``registry`` as the authoritative app-owned cache (post-admin apply).

        Keeps ``_provider_registry`` aligned with ``app.state.provider_registry`` and
        restarts discovery warmup like startup.
        """
        self._provider_registry = registry
        self.app.state.provider_registry = registry
        registry.start_model_list_refresh(settings)

    async def shutdown(self) -> None:
        verbose = self.settings.log_api_error_tracebacks
        if self.message_handler is not None:
            try:
                self.message_handler.session_store.flush_pending_save()
            except Exception as e:
                if verbose:
                    logger.warning("Session store flush on shutdown: {}", e)
                else:
                    logger.warning(
                        "Session store flush on shutdown: exc_type={}",
                        type(e).__name__,
                    )

        logger.info("Shutdown requested, cleaning up...")
        if self.messaging_platform:
            await best_effort(
                "messaging_platform.stop",
                self.messaging_platform.stop(),
                log_verbose_errors=verbose,
            )
        if self.cli_manager:
            await best_effort(
                "cli_manager.stop_all",
                self.cli_manager.stop_all(),
                log_verbose_errors=verbose,
            )
        state_registry = getattr(self.app.state, "provider_registry", None)
        registry_for_cleanup = (
            state_registry
            if isinstance(state_registry, ProviderRegistry)
            else self._provider_registry
        )
        if registry_for_cleanup is not None:
            await best_effort(
                "provider_registry.cleanup",
                registry_for_cleanup.cleanup(),
                log_verbose_errors=verbose,
            )
        await self._shutdown_limiter()
        reset_structured_trace_settings()
        logger.info("Server shut down cleanly")

    async def _start_messaging_if_configured(self) -> None:
        try:
            from messaging.bootstrap import create_optional_messaging_platform

            self.messaging_platform = create_optional_messaging_platform(self.settings)

            if self.messaging_platform:
                await self._start_message_handler()

        except ImportError as e:
            if self.settings.log_api_error_tracebacks:
                logger.warning("Messaging module import error: {}", e)
            else:
                logger.warning(
                    "Messaging module import error: exc_type={}",
                    type(e).__name__,
                )
        except Exception as e:
            if self.settings.log_api_error_tracebacks:
                logger.error("Failed to start messaging platform: {}", e)
                import traceback

                logger.error(traceback.format_exc())
            else:
                logger.error(
                    "Failed to start messaging platform: exc_type={}",
                    type(e).__name__,
                )

    async def _start_message_handler(self) -> None:
        from api.messaging_startup import start_messaging_handler_stack

        await start_messaging_handler_stack(self)

    def _publish_state(self) -> None:
        self.app.state.messaging_platform = self.messaging_platform
        self.app.state.message_handler = self.message_handler
        self.app.state.cli_manager = self.cli_manager

    async def _shutdown_limiter(self) -> None:
        verbose = self.settings.log_api_error_tracebacks
        try:
            from messaging.limiter import MessagingRateLimiter
        except Exception as e:
            if verbose:
                logger.debug(
                    "Rate limiter shutdown skipped (import failed): {}: {}",
                    type(e).__name__,
                    e,
                )
            else:
                logger.debug(
                    "Rate limiter shutdown skipped (import failed): exc_type={}",
                    type(e).__name__,
                )
            return

        await best_effort(
            "MessagingRateLimiter.shutdown_instance",
            MessagingRateLimiter.shutdown_instance(),
            timeout_s=2.0,
            log_verbose_errors=verbose,
        )
