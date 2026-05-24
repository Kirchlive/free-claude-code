"""Tests for the per-model context-window resolver."""

from unittest.mock import patch

from config.context_window import apply_context_window_env, resolve_max_context_tokens
from config.settings import Settings


def _settings(**kwargs) -> Settings:
    return Settings.model_construct(**kwargs)


def test_override_wins() -> None:
    settings = _settings(
        claude_code_max_context_tokens=500000, model="openai_codex/gpt-5.5"
    )
    with patch("config.context_window.context_window_for", return_value=272_000):
        assert resolve_max_context_tokens(settings) == 500000


def test_resolved_window_for_active_model() -> None:
    settings = _settings(claude_code_max_context_tokens=0, model="openai_codex/gpt-5.5")
    with patch(
        "config.context_window.context_window_for", return_value=272_000
    ) as mock_resolve:
        assert resolve_max_context_tokens(settings) == 272_000
    mock_resolve.assert_called_once_with("openai_codex/gpt-5.5")


def test_zero_when_no_window_known() -> None:
    settings = _settings(claude_code_max_context_tokens=0, model="lmstudio/local-model")
    with patch("config.context_window.context_window_for", return_value=None):
        assert resolve_max_context_tokens(settings) == 0


def test_apply_sets_max_tokens_and_disable_compact() -> None:
    env: dict[str, str] = {}
    apply_context_window_env(env, 272_000)
    assert env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "272000"
    assert env["DISABLE_COMPACT"] == "1"


def test_apply_is_noop_for_zero() -> None:
    env: dict[str, str] = {}
    apply_context_window_env(env, 0)
    assert env == {}
