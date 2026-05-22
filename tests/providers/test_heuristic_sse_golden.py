"""Snapshot-style coverage for heuristic OpenAI tool_use → Anthropic SSE."""

from __future__ import annotations

import json
from typing import Any

import pytest

from core.anthropic import SSEBuilder
from providers.openai_compat_heuristic_sse import iter_heuristic_tool_use_sse


def _json_after_data(evt: str) -> Any:
    data_line = next(line for line in evt.splitlines() if line.startswith("data:"))
    return json.loads(data_line.partition("data:")[2].strip())


@pytest.fixture
def sse() -> SSEBuilder:
    return SSEBuilder("msg_golden_fixture", "golden-model")


def test_iter_heuristic_tool_use_sse_three_part_shape(sse: SSEBuilder) -> None:
    tool = {"id": "t1", "name": "Read", "input": {"path": "README.md"}}
    events = list(iter_heuristic_tool_use_sse(sse, tool))
    assert len(events) == 3
    assert events[0].startswith("event: content_block_start\n")
    assert events[1].startswith("event: content_block_delta\n")
    assert events[2].startswith("event: content_block_stop\n")

    start = _json_after_data(events[0])
    assert start["type"] == "content_block_start"
    block = start["content_block"]
    assert isinstance(block, dict)
    assert block["type"] == "tool_use"
    assert block["id"] == "t1"
    assert block["name"] == "Read"
    assert block["input"] == {}

    delta = _json_after_data(events[1])
    assert delta["type"] == "content_block_delta"
    partial_raw = delta["delta"]["partial_json"]
    assert isinstance(partial_raw, str)
    assert json.loads(partial_raw) == {"path": "README.md"}

    stop = _json_after_data(events[2])
    assert stop["type"] == "content_block_stop"


def test_iter_heuristic_task_tool_forces_foreground_when_default_true(
    sse: SSEBuilder,
) -> None:
    tool = {
        "id": "task1",
        "name": "Task",
        "input": {"description": "scout", "run_in_background": True},
    }
    events = list(iter_heuristic_tool_use_sse(sse, tool))
    delta_payload = _json_after_data(events[1])
    inp_raw = delta_payload["delta"]["partial_json"]
    assert isinstance(inp_raw, str)
    assert json.loads(inp_raw)["run_in_background"] is False
