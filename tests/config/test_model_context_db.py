"""Tests for the OpenRouter per-model context-window lookup (direct fetch)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from config import model_context_db as db


def _payload() -> dict:
    return {
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


def _fake_urlopen(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = False
    return cm


@pytest.fixture(autouse=True)
def _clear_memo():
    db._all_windows.cache_clear()
    yield
    db._all_windows.cache_clear()


def test_normalise_unifies_separators_and_takes_last_segment() -> None:
    assert db._normalise("openai/gpt-5.5") == "gpt-5-5"
    assert db._normalise("moonshotai/kimi-k2.6") == "kimi-k2-6"
    assert db._normalise("GLM_4.7") == "glm-4-7"


def test_windows_from_payload_prefers_top_provider() -> None:
    windows = db._windows_from_payload(_payload())
    assert windows["gpt-5-5"] == 1000000  # top_provider preferred
    assert windows["kimi-k2-6"] == 262144
    assert "broken" not in windows


def test_lookup_fetches_and_matches() -> None:
    with patch("urllib.request.urlopen", return_value=_fake_urlopen(_payload())):
        assert db.lookup_context_window("gpt-5.5") == 1000000
        assert db.lookup_context_window("openai/gpt-5.5") == 1000000
        assert db.lookup_context_window("kimi-k2-6") == 262144
        assert db.lookup_context_window("unknown-model") is None


def test_lookup_returns_none_on_fetch_error() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("no network")):
        assert db.lookup_context_window("gpt-5.5") is None
