"""Dependency injection for FastAPI.

Production HTTP handlers must resolve upstream models through
:class:`~providers.registry.ProviderRegistry` owned by :class:`~api.runtime.AppRuntime`
via :func:`resolve_provider` and an explicit ``Starlette`` app instance.

:func:`get_process_cached_provider` / :func:`get_process_cached_provider_for_type`
intentionally target the small :class:`~api.provider_process_cache`-backed fallback
for scripts, smoke harnesses, and unit tests — they must not appear in modules like
``api.routes`` or ``api.services``.
"""

import secrets

from fastapi import Depends, Request
from loguru import logger
from starlette.applications import Starlette

import api.provider_process_cache as _process_cache
from config.settings import Settings
from config.settings import get_settings as _get_settings
from core.anthropic import get_user_facing_error_message
from providers.base import BaseProvider
from providers.exceptions import (
    AuthenticationError,
    ServiceUnavailableError,
    UnknownProviderTypeError,
)
from providers.registry import PROVIDER_DESCRIPTORS, ProviderRegistry

from .ingress_errors import (
    GatewayInvalidProxyApiKey,
    GatewayMissingProxyApiKey,
    ProviderResolutionAuthFailure,
)

# Process-level provider cache: :mod:`api.provider_process_cache`.

_process_registry: ProviderRegistry | None = None
_process_providers_dict_id: int | None = None


def _process_scope_registry() -> ProviderRegistry:
    """Registry view over ``PROCESS_PROVIDERS``; rebuilds if the dict is rebound."""
    global _process_registry, _process_providers_dict_id
    pid = id(_process_cache.PROCESS_PROVIDERS)
    if _process_registry is None or _process_providers_dict_id != pid:
        _process_registry = ProviderRegistry(_process_cache.PROCESS_PROVIDERS)
        _process_providers_dict_id = pid
    return _process_registry


def get_settings() -> Settings:
    """Return cached :class:`~config.settings.Settings` (FastAPI-friendly alias)."""
    return _get_settings()


def resolve_provider(
    provider_type: str,
    *,
    app: Starlette | None,
    settings: Settings,
) -> BaseProvider:
    """Resolve a provider using the app-scoped registry when ``app`` is set.

    When ``app`` is not ``None``, the app-owned :attr:`app.state.provider_registry`
    must exist (installed by :class:`~api.runtime.AppRuntime` during startup).
    After a healthy startup :attr:`app.state.claude_proxy_runtime` refers to that
    same runtime so admin flows can rotate the registry consistently.
    Callers that construct a bare ``FastAPI`` without lifespan must set
    ``app.state.provider_registry`` explicitly.

    When ``app`` is ``None`` (no HTTP context), uses
    :data:`api.provider_process_cache.PROCESS_PROVIDERS` only.
    """
    if app is not None:
        reg = getattr(app.state, "provider_registry", None)
        if reg is None:
            raise ServiceUnavailableError(
                "Provider registry is not configured. Ensure AppRuntime startup ran "
                "or assign app.state.provider_registry for test apps."
            )
        return _resolve_with_registry(reg, provider_type, settings)
    return _resolve_with_registry(_process_scope_registry(), provider_type, settings)


def _resolve_with_registry(
    registry: ProviderRegistry, provider_type: str, settings: Settings
) -> BaseProvider:
    should_log_init = not registry.is_cached(provider_type)
    try:
        provider = registry.get(provider_type, settings)
    except AuthenticationError as e:
        # Provider :class:`~providers.exceptions.AuthenticationError` messages are
        # curated configuration hints (env var names, docs links), not upstream noise.
        detail = str(e).strip() or get_user_facing_error_message(e)
        raise ProviderResolutionAuthFailure(detail) from e
    except UnknownProviderTypeError:
        logger.error(
            "Unknown provider_type: '{}'. Supported: {}",
            provider_type,
            ", ".join(f"'{key}'" for key in PROVIDER_DESCRIPTORS),
        )
        raise
    if should_log_init:
        logger.info("Provider initialized: {}", provider_type)
    return provider


def get_process_cached_provider_for_type(provider_type: str) -> BaseProvider:
    """Get or create a provider in the process-level cache (no ``app``/Request).

    HTTP route handlers should call :func:`resolve_provider` with the active
    :attr:`request.app` (via :class:`~api.runtime.AppRuntime`) instead of this
    process-wide cache.
    """
    return resolve_provider(provider_type, app=None, settings=get_settings())


def require_api_key(
    request: Request, settings: Settings = Depends(get_settings)
) -> None:
    """Require a server API key (Anthropic-style).

    Checks `x-api-key` header or `Authorization: Bearer ...` against
    `Settings.anthropic_auth_token`. If `ANTHROPIC_AUTH_TOKEN` is empty, this is a no-op.
    """
    anthropic_auth_token = settings.anthropic_auth_token
    if not anthropic_auth_token:
        # No API key configured -> allow
        return

    header = (
        request.headers.get("x-api-key")
        or request.headers.get("authorization")
        or request.headers.get("anthropic-auth-token")
    )
    if not header:
        raise GatewayMissingProxyApiKey()

    # Support both raw key in X-API-Key and Bearer token in Authorization
    token = header
    if header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1]

    # Strip anything after the first colon to handle tokens with appended model names
    if token and ":" in token:
        token = token.split(":", 1)[0]

    # Constant-time comparison to avoid leaking the configured token via
    # response-time differences on a per-byte mismatch (CWE-208).
    if not secrets.compare_digest(
        token.encode("utf-8"), anthropic_auth_token.encode("utf-8")
    ):
        raise GatewayInvalidProxyApiKey()


def get_process_cached_provider() -> BaseProvider:
    """Get or create the default provider (``MODEL`` / ``provider_type``).

    Process-cache helper for scripts, unit tests, and non-FastAPI callers. HTTP
    handlers must use :func:`resolve_provider` with :attr:`request.app` so the
    app-scoped :class:`~providers.registry.ProviderRegistry` is used.
    """
    return get_process_cached_provider_for_type(get_settings().provider_type)


async def cleanup_provider():
    """Cleanup process-level cached providers (:mod:`api.provider_process_cache`).

    Does not dispose :attr:`Starlette.state.provider_registry` — use that registry's
    :meth:`~providers.registry.ProviderRegistry.cleanup` instead (handled on
    server shutdown and admin reload).
    """
    await _process_cache.cleanup_process_providers()
    logger.debug("Process-level provider cleanup completed")
