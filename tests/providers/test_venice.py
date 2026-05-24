"""Tests for Venice AI (OpenAI-compatible) provider."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.anthropic.stream_contracts import (
    assert_anthropic_stream_contract,
    has_tool_use,
    parse_sse_text,
    text_content,
)
from providers.base import ProviderConfig
from providers.defaults import VENICE_DEFAULT_BASE
from providers.venice import VeniceProvider
from providers.venice.request import build_request_body


class MockMessage:
    def __init__(self, role, content):
        self.role = role
        self.content = content


class MockRequest:
    def __init__(self, **kwargs):
        self.model = "venice-uncensored"
        self.messages = [MockMessage("user", "Hello")]
        self.max_tokens = 100
        self.temperature = 0.5
        self.top_p = 0.9
        self.system = "System prompt"
        self.stop_sequences = None
        self.tools = []
        self.thinking = MagicMock()
        self.thinking.enabled = True
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def venice_config():
    return ProviderConfig(
        api_key="test_venice_key",
        base_url=VENICE_DEFAULT_BASE,
        rate_limit=10,
        rate_window=60,
        enable_thinking=True,
    )


@pytest.fixture(autouse=True)
def mock_rate_limiter():
    """Mock the global rate limiter to prevent waiting."""

    @asynccontextmanager
    async def _slot():
        yield

    with patch("providers.openai_compat.GlobalRateLimiter") as mock:
        instance = mock.get_scoped_instance.return_value

        async def _passthrough(fn, *args, **kwargs):
            return await fn(*args, **kwargs)

        instance.execute_with_retry = AsyncMock(side_effect=_passthrough)
        instance.concurrency_slot.side_effect = _slot
        yield instance


@pytest.fixture
def venice_provider(venice_config):
    return VeniceProvider(venice_config)


def test_init(venice_config):
    """Provider initializes the OpenAI client with Venice base URL and key."""
    with patch("providers.openai_compat.AsyncOpenAI") as mock_openai:
        provider = VeniceProvider(venice_config)
        assert provider._api_key == "test_venice_key"
        assert provider._base_url == "https://api.venice.ai/api/v1"
        assert provider._provider_name == "VENICE"
        mock_openai.assert_called_once()


def test_default_base_url_constant():
    assert VENICE_DEFAULT_BASE == "https://api.venice.ai/api/v1"


def test_build_request_body_basic(venice_provider):
    """Body is OpenAI-shaped: model preserved, system prepended as a message."""
    req = MockRequest()
    body = venice_provider._build_request_body(req)

    assert body["model"] == "venice-uncensored"
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][0]["content"] == "System prompt"
    assert body["messages"][1]["role"] == "user"


def _request_with_assistant_reasoning() -> MockRequest:
    return MockRequest(
        messages=[
            MockMessage("user", "hi"),
            MockMessage(
                "assistant",
                [
                    {"type": "thinking", "thinking": "SECRET_REASON"},
                    {"type": "text", "text": "ok"},
                ],
            ),
            MockMessage("user", "more"),
        ]
    )


def test_build_request_body_thinking_replays_reasoning():
    """thinking_enabled=True replays assistant reasoning via reasoning_content."""
    body = build_request_body(
        _request_with_assistant_reasoning(), thinking_enabled=True
    )

    assert any(
        msg.get("reasoning_content") == "SECRET_REASON" for msg in body["messages"]
    )


def test_build_request_body_no_thinking_drops_reasoning():
    """thinking_enabled=False drops assistant reasoning entirely (DISABLED replay)."""
    body = build_request_body(
        _request_with_assistant_reasoning(), thinking_enabled=False
    )

    assert all("reasoning_content" not in msg for msg in body["messages"])
    assert not any("SECRET_REASON" in str(msg) for msg in body["messages"])


@pytest.mark.asyncio
async def test_stream_response_text_contract(venice_provider):
    """A basic text stream is a valid Anthropic SSE stream carrying the text."""
    req = MockRequest()

    mock_chunk = MagicMock()
    mock_chunk.choices = [
        MagicMock(
            delta=MagicMock(
                content="Hello back!",
                reasoning_content=None,
                tool_calls=None,
            ),
            finish_reason="stop",
        )
    ]
    mock_chunk.usage = MagicMock(completion_tokens=5, prompt_tokens=10)

    async def mock_stream():
        yield mock_chunk

    with patch.object(
        venice_provider._client.chat.completions, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_stream()

        events = [event async for event in venice_provider.stream_response(req)]

    parsed = parse_sse_text("".join(events))
    assert_anthropic_stream_contract(parsed)
    assert text_content(parsed) == "Hello back!"


@pytest.mark.asyncio
async def test_stream_response_tool_use(venice_provider):
    """A native tool_call stream surfaces a tool_use block and stays contract-valid."""
    req = MockRequest()

    fn = MagicMock()
    fn.name = "get_weather"
    fn.arguments = '{"location": "Paris"}'
    tool_call = MagicMock(index=0, id="call_1", function=fn)

    mock_chunk = MagicMock()
    mock_chunk.choices = [
        MagicMock(
            delta=MagicMock(
                content=None,
                reasoning_content=None,
                tool_calls=[tool_call],
            ),
            finish_reason="tool_calls",
        )
    ]
    mock_chunk.usage = MagicMock(completion_tokens=5, prompt_tokens=10)

    async def mock_stream():
        yield mock_chunk

    with patch.object(
        venice_provider._client.chat.completions, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = mock_stream()

        events = [event async for event in venice_provider.stream_response(req)]

    parsed = parse_sse_text("".join(events))
    assert_anthropic_stream_contract(parsed)
    assert has_tool_use(parsed)


@pytest.mark.asyncio
async def test_cleanup(venice_provider):
    venice_provider._client = AsyncMock()

    await venice_provider.cleanup()

    venice_provider._client.close.assert_called_once()
