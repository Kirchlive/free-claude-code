"""Resolve the context window to advertise to the launched Claude Code CLI.

Claude Code assumes a fixed (~200k) context window for gateway model ids and cannot
be told the real window via ``/v1/models``. The supported lever is the
``CLAUDE_CODE_MAX_CONTEXT_TOKENS`` env var, which only takes effect together with
``DISABLE_COMPACT``.

The window is resolved per active model: explicit override
(``claude_code_max_context_tokens``) > the model's window from the OpenRouter context
DB (:mod:`config.model_context_db`) > 0 (leave Claude Code's native behavior). The
value follows the default ``MODEL`` at launch; a mid-session ``/model`` switch does not
update it.
"""

from __future__ import annotations

from collections.abc import MutableMapping

from config.model_context_db import context_window_for
from config.settings import Settings


def resolve_max_context_tokens(settings: Settings) -> int:
    """Return the context window (tokens) to force, or 0 to keep Claude Code's default.

    Order: explicit override > curated/OpenRouter window for the active model > 0.
    """
    if settings.claude_code_max_context_tokens > 0:
        return settings.claude_code_max_context_tokens
    return context_window_for(settings.model or "") or 0


def apply_context_window_env(env: MutableMapping[str, str], value: int) -> None:
    """Set ``CLAUDE_CODE_MAX_CONTEXT_TOKENS`` (+ required ``DISABLE_COMPACT``) when value > 0."""
    if value > 0:
        env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] = str(value)
        env["DISABLE_COMPACT"] = "1"
