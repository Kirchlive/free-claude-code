"""OpenAI via Codex OAuth provider.

Streams from the ChatGPT Codex Responses API (``https://chatgpt.com/backend-api/codex``)
using the OAuth session stored by the local ``codex`` CLI in ``~/.codex/auth.json``
(no API key). Converts the Responses streaming protocol into Anthropic SSE, so the
proxy can route Claude Code requests to a ChatGPT subscription with full tool_use
and thinking support.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.anthropic import append_request_id
from core.anthropic.sse import SSEBuilder
from core.trace import trace_event
from providers.base import BaseProvider, ProviderConfig
from providers.error_mapping import (
    map_error,
    user_visible_message_for_mapped_provider_error,
)
from providers.exceptions import AuthenticationError, ModelListResponseError
from providers.rate_limit import GlobalRateLimiter

from .oauth import CodexOAuth
from .responses import ResponsesStreamConverter, build_request_body

_DEFAULT_BASE = "https://chatgpt.com/backend-api/codex"
# The Codex backend requires a ``client_version`` query param and rejects requests
# below its ``minimal_client_version``. Bump when the backend raises the floor.
_CLIENT_VERSION = "0.133.0"


def _parse_model_slugs(payload: Any, *, provider_name: str) -> frozenset[str]:
    """Parse the Codex ``GET /models`` body shape ``{"models": [{"slug": ...}]}``."""
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise ModelListResponseError(
            f"{provider_name} model-list response is malformed: expected 'models' array"
        )
    slugs = {
        m["slug"]
        for m in models
        if isinstance(m, dict) and isinstance(m.get("slug"), str) and m["slug"].strip()
    }
    if not slugs:
        raise ModelListResponseError(
            f"{provider_name} model-list response had no model slugs"
        )
    return frozenset(slugs)


def _parse_event(data_lines: list[str]) -> dict[str, Any] | None:
    if not data_lines:
        return None
    payload = "\n".join(data_lines).strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class OpenAICodexProvider(BaseProvider):
    """OpenAI Codex (ChatGPT OAuth) provider using the Responses API."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._provider_name = "OPENAI_CODEX"
        self._base_url = (config.base_url or _DEFAULT_BASE).rstrip("/")
        self._oauth = CodexOAuth(config.credential_file or "~/.codex/auth.json")
        self._session_id = str(uuid.uuid4())
        self._global_rate_limiter = GlobalRateLimiter.get_scoped_instance(
            self._provider_name.lower(),
            rate_limit=config.rate_limit,
            rate_window=config.rate_window,
            max_concurrency=config.max_concurrency,
        )
        self._client = httpx.AsyncClient(
            proxy=config.proxy or None,
            timeout=httpx.Timeout(
                config.http_read_timeout,
                connect=config.http_connect_timeout,
                read=config.http_read_timeout,
                write=config.http_write_timeout,
            ),
        )

    async def cleanup(self) -> None:
        """Release HTTP client resources."""
        await self._client.aclose()

    def _headers(self, token: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "originator": "codex_cli_rs",
            "openai-beta": "responses=experimental",
            "user-agent": "free-claude-code/2.0 (+codex-oauth)",
            "session_id": self._session_id,
            "x-codex": "1",
        }
        account_id = self._oauth.account_id()
        if account_id:
            headers["chatgpt-account-id"] = account_id
        return headers

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        return build_request_body(
            request,
            thinking_enabled=self._is_thinking_enabled(request, thinking_enabled),
        )

    def _models_headers(self, token: str) -> dict[str, str]:
        """JSON headers for ``GET /models`` (distinct from the SSE responses headers)."""
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "originator": "codex_cli_rs",
            "user-agent": "free-claude-code/2.0 (+codex-oauth)",
        }
        account_id = self._oauth.account_id()
        if account_id:
            headers["chatgpt-account-id"] = account_id
        return headers

    async def list_model_ids(self) -> frozenset[str]:
        """Return advertised model slugs from ``GET /models`` (with one auth refresh)."""
        url = f"{self._base_url}/models"
        params = {"client_version": _CLIENT_VERSION}
        response = await self._client.get(
            url,
            headers=self._models_headers(self._oauth.access_token()),
            params=params,
        )
        if response.status_code == 401:
            token = await self._oauth.refresh(self._client)
            response = await self._client.get(
                url, headers=self._models_headers(token), params=params
            )
        response.raise_for_status()
        return _parse_model_slugs(response.json(), provider_name=self._provider_name)

    async def _open_stream(self, body: dict[str, Any]) -> httpx.Response:
        """Open the streaming ``/responses`` request, refreshing once on 401."""
        url = f"{self._base_url}/responses"
        params = {"client_version": _CLIENT_VERSION}
        token = self._oauth.access_token()
        request = self._client.build_request(
            "POST", url, json=body, headers=self._headers(token), params=params
        )
        response = await self._client.send(request, stream=True)
        if response.status_code == 401:
            if not response.is_closed:
                await response.aclose()
            token = await self._oauth.refresh(self._client)
            request = self._client.build_request(
                "POST", url, json=body, headers=self._headers(token), params=params
            )
            response = await self._client.send(request, stream=True)
        if response.status_code != 200:
            try:
                response.raise_for_status()
            finally:
                if not response.is_closed:
                    await response.aclose()
        return response

    async def _iter_events(
        self, response: httpx.Response
    ) -> AsyncIterator[dict[str, Any]]:
        data_lines: list[str] = []
        async for line in response.aiter_lines():
            if line == "":
                event = _parse_event(data_lines)
                data_lines = []
                if event is not None:
                    yield event
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        event = _parse_event(data_lines)
        if event is not None:
            yield event

    def _error_message(self, error: Exception, request_id: str | None) -> str:
        """Map a transport/auth error to a user-facing message."""
        if isinstance(error, AuthenticationError):
            base_message = error.message
        else:
            mapped = map_error(error, rate_limiter=self._global_rate_limiter)
            base_message = user_visible_message_for_mapped_provider_error(
                mapped,
                provider_name=self._provider_name,
                read_timeout_s=self._config.http_read_timeout,
            )
        return append_request_id(base_message, request_id)

    async def stream_response(
        self,
        request: Any,
        input_tokens: int = 0,
        *,
        request_id: str | None = None,
        thinking_enabled: bool | None = None,
    ) -> AsyncIterator[str]:
        """Stream a Codex Responses turn as Anthropic SSE."""
        enabled = self._is_thinking_enabled(request, thinking_enabled)
        body = build_request_body(request, thinking_enabled=enabled)
        sse = SSEBuilder(
            f"msg_{uuid.uuid4()}",
            request.model,
            input_tokens,
            log_raw_events=self._config.log_raw_sse_events,
        )
        converter = ResponsesStreamConverter(sse, thinking_enabled=enabled)
        req_tag = f" request_id={request_id}" if request_id else ""

        trace_event(
            stage="provider",
            event="provider.request.sent",
            source="provider",
            provider=self._provider_name,
            gateway_model=request.model,
            downstream_model=body.get("model"),
            message_count=len(body.get("input", [])),
            tool_count=len(body.get("tools", [])),
        )

        yield sse.message_start()

        # The ChatGPT-Codex backend occasionally drops the connection mid-stream
        # (RemoteProtocolError) during long reasoning before any content arrives.
        # Retry once when nothing has been emitted yet; re-running is safe because
        # message_start carries no content and the converter state is still pristine.
        produced_any = False
        max_attempts = 2
        async with self._global_rate_limiter.concurrency_slot():
            for attempt in range(max_attempts):
                response: httpx.Response | None = None
                try:
                    response = await self._open_stream(body)
                    async for event in self._iter_events(response):
                        for out in converter.feed(event):
                            produced_any = True
                            yield out
                    for out in converter.finish():
                        yield out
                    return
                except asyncio.CancelledError, GeneratorExit:
                    raise
                except (httpx.RemoteProtocolError, httpx.ReadError) as error:
                    self._log_stream_transport_error(
                        self._provider_name, req_tag, error, request_id=request_id
                    )
                    can_retry = (
                        attempt + 1 < max_attempts
                        and not produced_any
                        and not converter.has_emitted_content()
                    )
                    if can_retry:
                        if response is not None and not response.is_closed:
                            await response.aclose()
                        trace_event(
                            stage="provider",
                            event="provider.stream.retry",
                            source="provider",
                            provider=self._provider_name,
                            attempt=attempt + 1,
                            exc_type=type(error).__name__,
                        )
                        continue
                    for out in converter.emit_error_tail(
                        self._error_message(error, request_id)
                    ):
                        yield out
                    return
                except Exception as error:
                    self._log_stream_transport_error(
                        self._provider_name, req_tag, error, request_id=request_id
                    )
                    for out in converter.emit_error_tail(
                        self._error_message(error, request_id)
                    ):
                        yield out
                    return
                finally:
                    if response is not None and not response.is_closed:
                        await response.aclose()
