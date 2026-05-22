"""Golden-style checks for small native SSE policy helpers."""

from __future__ import annotations

from core.anthropic.native_sse_block_policy import (
    format_native_sse_event,
    is_terminal_openrouter_done_event,
    parse_native_sse_event,
)


def test_format_and_parse_native_sse_roundtrip() -> None:
    payload = '{"type": "content_block_delta", "index": 0}'
    block = format_native_sse_event("message_delta", payload)
    name, body = parse_native_sse_event(block)
    assert name == "message_delta"
    assert body == payload


def test_is_terminal_openrouter_done_event_truth_table() -> None:
    assert is_terminal_openrouter_done_event(None, "[DONE]")
    assert is_terminal_openrouter_done_event("done", "[done]")
    assert not is_terminal_openrouter_done_event("message_delta", "{}")
    assert not is_terminal_openrouter_done_event(None, '{"type":"x"}')
