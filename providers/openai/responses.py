"""Anthropic <-> OpenAI Responses API translation for the Codex provider.

Build requests for ``POST /responses`` from an Anthropic Messages request, and
convert the Responses streaming events back into Anthropic SSE via ``SSEBuilder``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from core.anthropic.content import get_block_attr, get_block_type
from core.anthropic.sse import SSEBuilder

# ============================ Request building ============================


def _system_instructions(system: Any) -> str | None:
    if isinstance(system, str):
        return system or None
    if isinstance(system, list):
        parts = [
            get_block_attr(block, "text", "")
            for block in system
            if get_block_type(block) == "text"
        ]
        text = "\n\n".join(part for part in parts if part)
        return text or None
    return None


def _serialize_tool_result(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            else:
                parts.append(json.dumps(item, default=str, ensure_ascii=False))
        return "\n".join(parts)
    return json.dumps(content, default=str, ensure_ascii=False)


def _tool_field(tool: Any, name: str) -> Any:
    if isinstance(tool, dict):
        return tool.get(name)
    return getattr(tool, name, None)


def _convert_tools(tools: Any) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        name = _tool_field(tool, "name")
        if not isinstance(name, str) or not name:
            continue
        schema = _tool_field(tool, "input_schema")
        converted.append(
            {
                "type": "function",
                "name": name,
                "description": _tool_field(tool, "description") or "",
                "parameters": schema
                if isinstance(schema, dict)
                else {"type": "object", "properties": {}},
            }
        )
    return converted


def _convert_tool_choice(tool_choice: Any) -> Any:
    if not isinstance(tool_choice, dict):
        return None
    choice_type = tool_choice.get("type")
    if choice_type == "auto":
        return "auto"
    if choice_type == "any":
        return "required"
    if choice_type == "none":
        return "none"
    if choice_type == "tool" and tool_choice.get("name"):
        return {"type": "function", "name": tool_choice["name"]}
    return None


def _convert_input(messages: Any) -> list[dict[str, Any]]:
    """Convert Anthropic messages to Responses ``input`` items (text + tool history)."""
    items: list[dict[str, Any]] = []
    for msg in messages:
        role = getattr(msg, "role", None)
        content = getattr(msg, "content", None)

        if isinstance(content, str):
            block_type = "input_text" if role == "user" else "output_text"
            items.append(
                {
                    "type": "message",
                    "role": role,
                    "content": [{"type": block_type, "text": content}],
                }
            )
            continue
        if not isinstance(content, list):
            continue

        text_parts: list[str] = []

        def flush(parts: list[str], current_role: str | None = role) -> None:
            if not parts:
                return
            block_type = "input_text" if current_role == "user" else "output_text"
            items.append(
                {
                    "type": "message",
                    "role": current_role,
                    "content": [{"type": block_type, "text": "\n".join(parts)}],
                }
            )
            parts.clear()

        for block in content:
            block_type = get_block_type(block)
            if block_type == "text":
                text_parts.append(get_block_attr(block, "text", ""))
            elif block_type == "tool_use" and role == "assistant":
                flush(text_parts)
                tool_input = get_block_attr(block, "input", {})
                items.append(
                    {
                        "type": "function_call",
                        "call_id": get_block_attr(block, "id"),
                        "name": get_block_attr(block, "name"),
                        "arguments": json.dumps(tool_input)
                        if isinstance(tool_input, dict)
                        else str(tool_input),
                    }
                )
            elif block_type == "tool_result" and role == "user":
                flush(text_parts)
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": get_block_attr(block, "tool_use_id"),
                        "output": _serialize_tool_result(
                            get_block_attr(block, "content", "")
                        ),
                    }
                )
            # thinking / redacted_thinking are not replayed to the Responses API.
        flush(text_parts)
    return items


def build_request_body(request: Any, *, thinking_enabled: bool) -> dict[str, Any]:
    """Build a ``POST /responses`` body from an Anthropic Messages request."""
    body: dict[str, Any] = {
        "model": request.model,
        "input": _convert_input(request.messages),
        "stream": True,
        "store": False,
    }

    # The Codex backend rejects requests without instructions ("Instructions are
    # required"); fall back to a neutral default when no system prompt is provided.
    instructions = _system_instructions(getattr(request, "system", None))
    body["instructions"] = instructions or "You are a helpful coding assistant."

    tools = _convert_tools(getattr(request, "tools", None))
    if tools:
        body["tools"] = tools
        tool_choice = _convert_tool_choice(getattr(request, "tool_choice", None))
        if tool_choice is not None:
            body["tool_choice"] = tool_choice

    if thinking_enabled:
        body["reasoning"] = {"effort": "medium", "summary": "auto"}

    # The Codex backend rejects ``max_output_tokens`` ("Unsupported parameter"), so the
    # client's max_tokens is intentionally not forwarded.
    return body


# ============================ Streaming conversion ============================


class ResponsesStreamConverter:
    """Drive an ``SSEBuilder`` from OpenAI Responses streaming events.

    The caller emits ``message_start`` before feeding events; this converter maps
    text / reasoning / function-call events to Anthropic content blocks and emits
    the closing ``message_delta`` + ``message_stop`` on ``response.completed`` (or
    when :meth:`finish` is called after the stream ends).
    """

    def __init__(self, sse: SSEBuilder, *, thinking_enabled: bool) -> None:
        self._sse = sse
        self._thinking_enabled = thinking_enabled
        self._tool_outputs: set[int] = set()
        self._stopped_tools: set[int] = set()
        self._any_tool = False
        self._output_tokens: int | None = None
        self._finished = False

    def feed(self, event: dict[str, Any]) -> Iterator[str]:
        etype = event.get("type")

        if etype == "response.output_text.delta":
            yield from self._sse.ensure_text_block()
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                yield self._sse.emit_text_delta(delta)
            return

        if etype in (
            "response.reasoning_summary_text.delta",
            "response.reasoning_text.delta",
        ):
            if not self._thinking_enabled:
                return
            yield from self._sse.ensure_thinking_block()
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                yield self._sse.emit_thinking_delta(delta)
            return

        if etype == "response.output_item.added":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "function_call":
                out_idx = self._output_index(event)
                yield from self._sse.close_content_blocks()
                call_id = str(
                    item.get("call_id") or item.get("id") or f"call_{out_idx}"
                )
                name = str(item.get("name") or "")
                yield self._sse.start_tool_block(out_idx, call_id, name)
                self._tool_outputs.add(out_idx)
                self._any_tool = True
            return

        if etype == "response.function_call_arguments.delta":
            out_idx = event.get("output_index")
            if isinstance(out_idx, int) and out_idx in self._tool_outputs:
                delta = event.get("delta")
                if isinstance(delta, str) and delta:
                    yield self._sse.emit_tool_delta(out_idx, delta)
            return

        if etype == "response.function_call_arguments.done":
            yield from self._stop_tool(event.get("output_index"))
            return

        if etype == "response.output_item.done":
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "function_call":
                yield from self._stop_tool(self._output_index(event))
            return

        if etype == "response.completed":
            response = event.get("response")
            usage = response.get("usage") if isinstance(response, dict) else None
            if isinstance(usage, dict) and isinstance(usage.get("output_tokens"), int):
                self._output_tokens = usage["output_tokens"]
            yield from self.finish()
            return

        if etype in ("error", "response.failed", "response.incomplete"):
            yield from self._emit_error(event)
            return

    def _output_index(self, event: dict[str, Any]) -> int:
        out_idx = event.get("output_index")
        if isinstance(out_idx, int):
            return out_idx
        return len(self._tool_outputs)

    def _stop_tool(self, out_idx: Any) -> Iterator[str]:
        if (
            isinstance(out_idx, int)
            and out_idx in self._tool_outputs
            and out_idx not in self._stopped_tools
        ):
            self._stopped_tools.add(out_idx)
            yield self._sse.stop_tool_block(out_idx)

    def _close_open(self) -> Iterator[str]:
        """Close open text/thinking blocks and any tool block not yet stopped."""
        yield from self._sse.close_content_blocks()
        for out_idx in sorted(self._tool_outputs - self._stopped_tools):
            self._stopped_tools.add(out_idx)
            yield self._sse.stop_tool_block(out_idx)

    def _emit_error(self, event: dict[str, Any]) -> Iterator[str]:
        error = event.get("error")
        message = "Provider request failed."
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            message = error["message"]
        yield from self._close_open()
        yield from self._sse.emit_error(message)
        yield from self.finish(emitted_error=True)

    def finish(
        self, *, stop_reason: str | None = None, emitted_error: bool = False
    ) -> Iterator[str]:
        """Close open blocks and emit the message tail (idempotent)."""
        if self._finished:
            return
        self._finished = True
        if not emitted_error:
            yield from self._close_open()
        if stop_reason is None:
            stop_reason = "tool_use" if self._any_tool else "end_turn"
        output_tokens = (
            self._output_tokens
            if self._output_tokens is not None
            else self._sse.estimate_output_tokens()
        )
        yield self._sse.message_delta(stop_reason, output_tokens)
        yield self._sse.message_stop()

    @property
    def finished(self) -> bool:
        return self._finished

    def emit_error_tail(self, message: str) -> Iterator[str]:
        """Emit an error text block + message tail for a transport-level failure."""
        if self._finished:
            return
        yield from self._close_open()
        yield from self._sse.emit_error(message)
        yield from self.finish(emitted_error=True)
