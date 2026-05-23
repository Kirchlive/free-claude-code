"""HTTP/SSE primitives for Anthropic-compatible native Messages streaming.

Used by :class:`~providers.anthropic_messages_transport.AnthropicMessagesTransport`;
keeps httpx iteration logic out of the transport class itself.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx


async def read_streaming_error_body_preview(
    response: httpx.Response, max_bytes: int
) -> tuple[bytes, bool]:
    """Read at most ``max_bytes`` from the error body for logging. Returns (preview, truncated)."""
    if max_bytes <= 0:
        return b"", False
    received = 0
    parts: list[bytes] = []
    truncated = False
    async for chunk in response.aiter_bytes(chunk_size=65_536):
        if received >= max_bytes:
            truncated = True
            break
        remaining = max_bytes - received
        take = chunk if len(chunk) <= remaining else chunk[:remaining]
        if take:
            parts.append(take)
        received += len(take)
        if len(chunk) > len(take):
            truncated = True
            break
        if received >= max_bytes:
            break
    return (b"".join(parts), truncated)


async def iter_sse_line_chunks(response: httpx.Response) -> AsyncIterator[str]:
    """Yield raw SSE line chunks preserving local provider behavior."""
    async for line in response.aiter_lines():
        if line:
            yield f"{line}\n"
        else:
            yield "\n"


async def iter_grouped_sse_events(response: httpx.Response) -> AsyncIterator[str]:
    """Group line-delimited SSE responses into full SSE events."""
    event_lines: list[str] = []
    async for line in response.aiter_lines():
        if line:
            event_lines.append(line)
            continue
        if event_lines:
            yield "\n".join(event_lines) + "\n\n"
            event_lines.clear()
    if event_lines:
        yield "\n".join(event_lines) + "\n\n"
