"""Tests for the OpenAI via Codex OAuth provider (Responses API transport)."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.anthropic.stream_contracts import (
    assert_anthropic_stream_contract,
    has_tool_use,
    parse_sse_text,
    text_content,
    thinking_content,
)
from providers.base import ProviderConfig
from providers.openai import OpenAICodexProvider


class MockMessage:
    def __init__(self, role, content):
        self.role = role
        self.content = content


class MockRequest:
    def __init__(self, **kwargs):
        self.model = "gpt-5.5"
        self.messages = [MockMessage("user", "Hello")]
        self.max_tokens = 100
        self.temperature = None
        self.top_p = None
        self.system = "Sys"
        self.stop_sequences = None
        self.tools = []
        self.tool_choice = None
        self.metadata = None
        self.thinking = MagicMock()
        self.thinking.enabled = True
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeResponse:
    def __init__(self, *, status_code=200, lines=None, text=""):
        self.status_code = status_code
        self._lines = lines or []
        self._text = text
        self.is_closed = False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    def raise_for_status(self):
        import httpx

        httpx.Response(
            self.status_code,
            request=httpx.Request(
                "POST", "https://chatgpt.com/backend-api/codex/responses"
            ),
            text=self._text,
        ).raise_for_status()

    async def aclose(self):
        self.is_closed = True


def _stream(events):
    lines: list[str] = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}")
        lines.append("")
    return FakeResponse(lines=lines)


@pytest.fixture
def auth_file(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "auth_mode": "ChatGPT",
                "tokens": {
                    "access_token": "tok-1",
                    "account_id": "acct-1",
                    "refresh_token": "refresh-1",
                },
                "last_refresh": "2026-05-24T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def config(auth_file):
    return ProviderConfig(
        api_key="",
        credential_file=str(auth_file),
        base_url="https://chatgpt.com/backend-api/codex",
        rate_limit=10,
        rate_window=60,
    )


@pytest.fixture(autouse=True)
def mock_rate_limiter():
    @asynccontextmanager
    async def _slot():
        yield

    with patch("providers.openai.client.GlobalRateLimiter") as mock:
        instance = mock.get_scoped_instance.return_value
        instance.concurrency_slot.side_effect = _slot
        yield instance


@pytest.fixture
def provider(config):
    return OpenAICodexProvider(config)


# ---------------------------------------------------------------- request body


def test_build_request_body_shapes_responses_payload(provider):
    req = MockRequest(
        tools=[
            {
                "name": "Read",
                "description": "read file",
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
        tool_choice={"type": "auto"},
    )
    body = provider._build_request_body(req)

    assert body["model"] == "gpt-5.5"
    assert body["stream"] is True
    assert body["store"] is False
    assert body["instructions"] == "Sys"
    assert body["input"][0]["role"] == "user"
    assert body["tools"][0] == {
        "type": "function",
        "name": "Read",
        "description": "read file",
        "parameters": {"type": "object", "properties": {}},
    }
    assert body["tool_choice"] == "auto"
    assert body["reasoning"] == {"effort": "medium", "summary": "auto"}
    assert "max_output_tokens" not in body


def test_build_request_body_omits_reasoning_when_thinking_disabled(provider):
    req = MockRequest()
    req.thinking.enabled = False
    body = provider._build_request_body(req)
    assert "reasoning" not in body


# ---------------------------------------------------------------- streaming


@pytest.mark.asyncio
async def test_stream_text(provider):
    response = _stream(
        [
            {"type": "response.output_text.delta", "delta": "Hello"},
            {"type": "response.output_text.delta", "delta": " world"},
            {"type": "response.completed", "response": {"usage": {"output_tokens": 5}}},
        ]
    )
    with (
        patch.object(provider._client, "build_request"),
        patch.object(
            provider._client, "send", new_callable=AsyncMock, return_value=response
        ),
    ):
        events = [e async for e in provider.stream_response(MockRequest())]

    parsed = parse_sse_text("".join(events))
    assert_anthropic_stream_contract(parsed)
    assert text_content(parsed) == "Hello world"
    assert response.is_closed


@pytest.mark.asyncio
async def test_stream_thinking(provider):
    response = _stream(
        [
            {"type": "response.reasoning_summary_text.delta", "delta": "pondering"},
            {"type": "response.output_text.delta", "delta": "Answer"},
            {"type": "response.completed", "response": {}},
        ]
    )
    with (
        patch.object(provider._client, "build_request"),
        patch.object(
            provider._client, "send", new_callable=AsyncMock, return_value=response
        ),
    ):
        events = [e async for e in provider.stream_response(MockRequest())]

    parsed = parse_sse_text("".join(events))
    assert_anthropic_stream_contract(parsed)
    assert "pondering" in thinking_content(parsed)
    assert "Answer" in text_content(parsed)


@pytest.mark.asyncio
async def test_stream_thinking_suppressed_when_disabled(provider):
    req = MockRequest()
    req.thinking.enabled = False
    response = _stream(
        [
            {"type": "response.reasoning_summary_text.delta", "delta": "secret"},
            {"type": "response.output_text.delta", "delta": "Answer"},
            {"type": "response.completed", "response": {}},
        ]
    )
    with (
        patch.object(provider._client, "build_request"),
        patch.object(
            provider._client, "send", new_callable=AsyncMock, return_value=response
        ),
    ):
        events = [e async for e in provider.stream_response(req)]

    text = "".join(events)
    assert "secret" not in text
    assert "Answer" in text


@pytest.mark.asyncio
async def test_stream_tool_use(provider):
    response = _stream(
        [
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {"type": "function_call", "call_id": "call_1", "name": "Read"},
            },
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 0,
                "delta": '{"path":"/tmp"}',
            },
            {"type": "response.function_call_arguments.done", "output_index": 0},
            {"type": "response.completed", "response": {"usage": {"output_tokens": 3}}},
        ]
    )
    with (
        patch.object(provider._client, "build_request"),
        patch.object(
            provider._client, "send", new_callable=AsyncMock, return_value=response
        ),
    ):
        events = [e async for e in provider.stream_response(MockRequest())]

    parsed = parse_sse_text("".join(events))
    assert_anthropic_stream_contract(parsed)
    assert has_tool_use(parsed)
    # stop_reason should reflect a tool call
    delta = next(p for p in parsed if p.event == "message_delta")
    assert delta.data["delta"]["stop_reason"] == "tool_use"


@pytest.mark.asyncio
async def test_text_then_tool_use(provider):
    response = _stream(
        [
            {"type": "response.output_text.delta", "delta": "Let me read it."},
            {
                "type": "response.output_item.added",
                "output_index": 1,
                "item": {"type": "function_call", "call_id": "call_9", "name": "Read"},
            },
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 1,
                "delta": '{"path":"/x"}',
            },
            {
                "type": "response.output_item.done",
                "output_index": 1,
                "item": {"type": "function_call"},
            },
            {"type": "response.completed", "response": {}},
        ]
    )
    with (
        patch.object(provider._client, "build_request"),
        patch.object(
            provider._client, "send", new_callable=AsyncMock, return_value=response
        ),
    ):
        events = [e async for e in provider.stream_response(MockRequest())]

    parsed = parse_sse_text("".join(events))
    assert_anthropic_stream_contract(parsed)
    assert "Let me read it." in text_content(parsed)
    assert has_tool_use(parsed)


# ---------------------------------------------------------------- auth refresh


@pytest.mark.asyncio
async def test_refresh_on_401_retries_and_persists(provider, auth_file):
    ok = _stream(
        [
            {"type": "response.output_text.delta", "delta": "hi"},
            {"type": "response.completed", "response": {}},
        ]
    )
    sends = [FakeResponse(status_code=401), ok]
    refresh_resp = MagicMock()
    refresh_resp.json.return_value = {
        "access_token": "tok-2",
        "refresh_token": "refresh-2",
    }
    refresh_resp.raise_for_status = MagicMock()
    build = MagicMock()

    with (
        patch.object(provider._client, "build_request", build),
        patch.object(
            provider._client, "send", new_callable=AsyncMock, side_effect=sends
        ),
        patch.object(
            provider._client, "post", new_callable=AsyncMock, return_value=refresh_resp
        ),
    ):
        events = [e async for e in provider.stream_response(MockRequest())]

    # Second request must use the refreshed token.
    second_headers = build.call_args_list[1].kwargs["headers"]
    assert second_headers["Authorization"] == "Bearer tok-2"
    # Refreshed token persisted atomically back to auth.json.
    saved = json.loads(auth_file.read_text(encoding="utf-8"))
    assert saved["tokens"]["access_token"] == "tok-2"
    assert saved["tokens"]["refresh_token"] == "refresh-2"

    parsed = parse_sse_text("".join(events))
    assert_anthropic_stream_contract(parsed)
    assert "hi" in text_content(parsed)


@pytest.mark.asyncio
async def test_missing_auth_file_surfaces_login_hint(tmp_path):
    config = ProviderConfig(
        api_key="",
        credential_file=str(tmp_path / "nope.json"),
        base_url="https://chatgpt.com/backend-api/codex",
    )
    with patch("providers.openai.client.GlobalRateLimiter") as mock_limiter:
        provider = OpenAICodexProvider(config)

    @asynccontextmanager
    async def _slot():
        yield

    mock_limiter.get_scoped_instance.return_value.concurrency_slot.side_effect = _slot

    events = [e async for e in provider.stream_response(MockRequest())]
    text = "".join(events)
    assert "message_start" in text and "message_stop" in text
    assert "codex login" in text


# ---------------------------------------------------------------- misc


@pytest.mark.asyncio
async def test_list_model_ids_parses_models_endpoint(provider):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "models": [{"slug": "gpt-5.5"}, {"slug": "gpt-5.5-codex"}]
    }
    resp.raise_for_status = MagicMock()
    with patch.object(
        provider._client, "get", new_callable=AsyncMock, return_value=resp
    ):
        ids = await provider.list_model_ids()
    assert "gpt-5.5" in ids
    assert "gpt-5.5-codex" in ids


@pytest.mark.asyncio
async def test_stream_error_path(provider):
    with (
        patch.object(provider._client, "build_request"),
        patch.object(
            provider._client,
            "send",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
    ):
        events = [e async for e in provider.stream_response(MockRequest())]

    text = "".join(events)
    assert "message_start" in text
    assert "message_stop" in text
    parsed = parse_sse_text(text)
    assert_anthropic_stream_contract(parsed, allow_error=True)
