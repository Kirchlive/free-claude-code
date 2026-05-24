"""Tests for the per-model context-window resolver."""

from config.context_window import apply_context_window_env, resolve_max_context_tokens
from config.settings import Settings


def _settings(**kwargs) -> Settings:
    return Settings.model_construct(**kwargs)


def test_override_wins_over_catalog() -> None:
    settings = _settings(
        claude_code_max_context_tokens=500000, model="openai_codex/gpt-5.5"
    )
    assert resolve_max_context_tokens(settings) == 500000


def test_catalog_default_for_openai_codex() -> None:
    settings = _settings(claude_code_max_context_tokens=0, model="openai_codex/gpt-5.5")
    assert resolve_max_context_tokens(settings) == 1_000_000


def test_zero_when_provider_has_no_catalog_window() -> None:
    settings = _settings(
        claude_code_max_context_tokens=0, model="nvidia_nim/meta/llama"
    )
    assert resolve_max_context_tokens(settings) == 0


def test_apply_sets_max_tokens_and_disable_compact() -> None:
    env: dict[str, str] = {}
    apply_context_window_env(env, 1_000_000)
    assert env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "1000000"
    assert env["DISABLE_COMPACT"] == "1"


def test_apply_is_noop_for_zero() -> None:
    env: dict[str, str] = {}
    apply_context_window_env(env, 0)
    assert env == {}
