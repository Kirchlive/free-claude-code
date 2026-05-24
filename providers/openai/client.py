"""OpenAI via Codex OAuth provider.

Streams from the ChatGPT Codex Responses API (``https://chatgpt.com/backend-api/codex``)
using the OAuth session stored by the local ``codex`` CLI in ``~/.codex/auth.json``
(no API key). Real implementation lands in the dedicated provider work item; this
module currently provides the typed surface so the registry can wire it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from providers.base import BaseProvider, ProviderConfig


class OpenAICodexProvider(BaseProvider):
    """OpenAI Codex (ChatGPT OAuth) provider using the Responses API."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._credential_file = config.credential_file

    async def cleanup(self) -> None:
        """Release resources (HTTP client added with the full implementation)."""
        return None

    async def list_model_ids(self) -> frozenset[str]:
        """Return advertised model ids (dynamic discovery added with full impl)."""
        return frozenset()

    async def stream_response(
        self,
        request: Any,
        input_tokens: int = 0,
        *,
        request_id: str | None = None,
        thinking_enabled: bool | None = None,
    ) -> AsyncIterator[str]:
        """Stream the response in Anthropic SSE format (full impl pending)."""
        if False:
            yield ""
