"""Tests for the OpenRouter-backed context-window DB."""

import json

from config import model_context_db as db


def test_normalise_unifies_separators_and_takes_last_segment() -> None:
    assert db._normalise("openai/gpt-5.5") == "gpt-5-5"
    assert db._normalise("moonshotai/kimi-k2.6") == "kimi-k2-6"
    assert db._normalise("GLM_4.7") == "glm-4-7"


def test_windows_from_payload_prefers_top_provider() -> None:
    payload = {
        "data": [
            {
                "id": "openai/gpt-5.5",
                "context_length": 1050000,
                "top_provider": {"context_length": 1000000},
            },
            {"id": "moonshotai/kimi-k2.6", "context_length": 262144},
            {"id": "broken"},  # no window -> skipped
        ]
    }
    windows = db._windows_from_payload(payload)
    assert windows["gpt-5-5"] == 1000000  # top_provider preferred
    assert windows["kimi-k2-6"] == 262144
    assert "broken" not in windows


def test_lookup_reads_cache(tmp_path, monkeypatch) -> None:
    cache = tmp_path / "openrouter_models.json"
    cache.write_text(
        json.dumps({"fetched_at": 9_999_999_999.0, "windows": {"gpt-5-5": 1000000}})
    )
    monkeypatch.setattr(db, "_cache_path", lambda: cache)

    assert db.lookup_context_window("gpt-5.5") == 1000000
    assert db.lookup_context_window("openai/gpt-5.5") == 1000000
    assert db.lookup_context_window("unknown-model") is None


def test_lookup_returns_none_without_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(db, "_cache_path", lambda: tmp_path / "missing.json")
    assert db.lookup_context_window("gpt-5.5") is None
