"""Resolve the context window to advertise to the launched Claude Code CLI.

Claude Code assumes a fixed (~200k) context window for gateway model ids and cannot
be told the real window via ``/v1/models``. The supported lever is the
``CLAUDE_CODE_MAX_CONTEXT_TOKENS`` env var, which only takes effect together with
``DISABLE_COMPACT``. This module resolves a window for the active default model and
applies those env vars to a child environment.

Resolution order: explicit override (``claude_code_max_context_tokens``) > per-provider
catalog default (``ProviderDescriptor.context_window``) > 0 (leave Claude Code's native
behavior). The value follows the default ``MODEL`` at launch; a mid-session ``/model``
switch does not update it.
"""

from __future__ import annotations

from collections.abc import MutableMapping

from config.provider_catalog import PROVIDER_CATALOG
from config.settings import Settings


def resolve_max_context_tokens(settings: Settings) -> int:
    """Return the context window (tokens) to force, or 0 to keep Claude Code's default."""
    if settings.claude_code_max_context_tokens > 0:
        return settings.claude_code_max_context_tokens
    model = settings.model or ""
    provider_id = model.split("/", 1)[0] if "/" in model else ""
    descriptor = PROVIDER_CATALOG.get(provider_id)
    if descriptor is not None and descriptor.context_window:
        return descriptor.context_window
    return 0


def apply_context_window_env(env: MutableMapping[str, str], value: int) -> None:
    """Set ``CLAUDE_CODE_MAX_CONTEXT_TOKENS`` (+ required ``DISABLE_COMPACT``) when value > 0."""
    if value > 0:
        env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(value)
        env["DISABLE_COMPACT"] = "1"
