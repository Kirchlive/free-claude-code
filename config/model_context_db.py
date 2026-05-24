"""Per-model context windows from OpenRouter's public ``/v1/models``.

OpenRouter is treated as always-available: a single GET returns ``context_length`` for
~all mainstream models, and we read the needed model's entry directly. The result is
memoised per process (model windows are stable); ``refresh()`` drops the memo so newly
integrated providers/models are picked up. Triggered when fcc-server (re)discovers
provider models; the launch path resolves the active model's window directly.

Matching is conservative: ids are normalised (lowercase, ``.``/``_`` -> ``-``, last
path segment only) and matched exactly, so divergent versions (e.g. ``glm4.7`` vs
``glm-5.1``) do not mis-map.
"""

from __future__ import annotations

import json
import urllib.request
from functools import lru_cache
from typing import Any

from loguru import logger

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_FETCH_TIMEOUT_SECONDS = 8.0


def _normalise(model_id: str) -> str:
    """Normalise a model id to its comparable key (last segment, unified separators)."""
    last = model_id.rsplit("/", 1)[-1].strip().lower()
    return last.replace(".", "-").replace("_", "-")


def _windows_from_payload(payload: Any) -> dict[str, int]:
    """Build {normalised_model_key: context_length} from an OpenRouter models payload."""
    data = payload.get("data") if isinstance(payload, dict) else None
    windows: dict[str, int] = {}
    if not isinstance(data, list):
        return windows
    for entry in data:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        top = entry.get("top_provider")
        window = None
        if isinstance(top, dict) and isinstance(top.get("context_length"), int):
            window = top["context_length"]
        elif isinstance(entry.get("context_length"), int):
            window = entry["context_length"]
        if isinstance(model_id, str) and window:
            windows[_normalise(model_id)] = window
    return windows


@lru_cache(maxsize=1)
def _all_windows() -> dict[str, int]:
    """Fetch the OpenRouter models list directly and return the window map (memoised)."""
    request = urllib.request.Request(
        OPENROUTER_MODELS_URL, headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        # Minimal guard so a local network error never blocks launching the CLI.
        logger.warning("OpenRouter models fetch failed: {}", type(exc).__name__)
        return {}
    return _windows_from_payload(payload)


def lookup_context_window(model_ref: str) -> int | None:
    """Fetch the OpenRouter entry for ``model_ref`` and return its context window.

    Returns None when the model cannot be confidently matched (caller falls back).
    """
    if not model_ref:
        return None
    return _all_windows().get(_normalise(model_ref)) or None


# Curated, deployment-authoritative windows that differ from OpenRouter's general spec,
# keyed by the full fcc ``provider/model`` ref (lowercased). The ChatGPT-Codex backend
# caps gpt-5.x at 272k regardless of the model's general 1M spec, so OpenRouter would
# overstate it. Verified via the codex /models endpoint (context_window field).
CURATED_CONTEXT_WINDOWS: dict[str, int] = {
    "openai_codex/gpt-5.5": 272_000,
    "openai_codex/gpt-5.4": 272_000,
    "openai_codex/gpt-5.4-mini": 272_000,
    "openai_codex/gpt-5.3-codex": 272_000,
    "openai_codex/gpt-5.2": 272_000,
    "openai_codex/codex-auto-review": 272_000,
}


def context_window_for(model_ref: str) -> int | None:
    """Resolve a model's context window: curated table first, then OpenRouter.

    ``model_ref`` is the full fcc ``provider/model`` ref. The curated table is
    authoritative for known/constrained deployments; OpenRouter is a best-effort
    fallback for everything else. Returns None when unknown (caller falls back).
    """
    if not model_ref:
        return None
    curated = CURATED_CONTEXT_WINDOWS.get(model_ref.strip().lower())
    if curated:
        return curated
    return lookup_context_window(model_ref)


def refresh() -> None:
    """Drop the memo and re-fetch (call when fcc-server (re)discovers provider models)."""
    _all_windows.cache_clear()
    _all_windows()
