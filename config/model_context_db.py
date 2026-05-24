"""OpenRouter-backed per-model context-window database.

OpenRouter's public ``/v1/models`` lists ``context_length`` for ~all mainstream
models. We use it as a per-model context-window source for gateway models, since
Claude Code assumes a fixed ~200k window for gateway model ids. The fcc-server side
populates/refreshes the local cache (daily TTL) when provider models are refreshed;
lookups are cache-only so the launch path stays fast and offline-safe.

Matching is conservative: we normalise both ids (lowercase, ``.``/``_`` -> ``-``,
last path segment only) and require an exact normalised match, so divergent versions
(e.g. ``glm4.7`` vs ``glm-5.1``) do not mis-map. No match -> ``None`` (caller falls back).
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from loguru import logger

from config.paths import config_dir_path

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_CACHE_TTL_SECONDS = 24 * 3600
_FETCH_TIMEOUT_SECONDS = 5.0


def _cache_path() -> Path:
    return config_dir_path() / "cache" / "openrouter_models.json"


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


def refresh(*, force: bool = False) -> dict[str, int]:
    """Fetch the OpenRouter models DB and write the cache. Returns the windows map.

    On network failure, returns any existing cached map (or empty) without raising.
    """
    path = _cache_path()
    if not force:
        cached = _load_cached(allow_stale=False)
        if cached is not None:
            return cached
    try:
        request = urllib.request.Request(
            OPENROUTER_MODELS_URL, headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("OpenRouter models DB fetch failed: {}", type(exc).__name__)
        stale = _load_cached(allow_stale=True)
        return stale if stale is not None else {}
    windows = _windows_from_payload(payload)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"fetched_at": time.time(), "windows": windows}),
            encoding="utf-8",
        )
        tmp.replace(path)
    except OSError as exc:
        logger.debug("OpenRouter models DB cache write failed: {}", type(exc).__name__)
    return windows


def _load_cached(*, allow_stale: bool) -> dict[str, int] | None:
    path = _cache_path()
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        windows = blob.get("windows")
        fetched_at = blob.get("fetched_at", 0)
    except OSError, ValueError:
        return None
    if not isinstance(windows, dict):
        return None
    if not allow_stale and (time.time() - float(fetched_at)) > _CACHE_TTL_SECONDS:
        return None
    return {str(k): int(v) for k, v in windows.items() if isinstance(v, int)}


def lookup_context_window(model_ref: str) -> int | None:
    """Return the context window for a model id from the cached OpenRouter DB.

    Cache-only (no network). Returns None when the cache is missing or the model
    cannot be confidently matched (caller should fall back).
    """
    if not model_ref:
        return None
    # Cache-only read (no network) so the launch path stays fast and offline-safe;
    # the cache is populated/refreshed by the fcc-server side via refresh().
    windows = _load_cached(allow_stale=True)
    if windows is None:
        return None
    return windows.get(_normalise(model_ref))
