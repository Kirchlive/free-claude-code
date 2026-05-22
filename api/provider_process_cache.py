"""Process-level provider cache for scripts and unit tests only.

HTTP request handlers MUST use ``request.app.state.provider_registry`` installed by
:class:`api.runtime.AppRuntime` via :func:`api.dependencies.resolve_provider` with
a non-null ``app``. This module retains a standalone cache only for ``app=None``
call paths (offline scripts, synchronous tests).

Always access the cache as ``provider_process_cache.PROCESS_PROVIDERS`` (module
attribute) so tests can rebind it for isolation.

See docs/ARCHITECTURE.md ("Provider lifecycle").
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from providers.registry import ProviderRegistry

if TYPE_CHECKING:
    from providers.base import BaseProvider

PROCESS_PROVIDERS: dict[str, BaseProvider] = {}


async def cleanup_process_providers() -> None:
    """Close cached providers held only in the process-level cache."""
    await ProviderRegistry(PROCESS_PROVIDERS).cleanup()
