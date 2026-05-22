"""Wafer provider implementation (native Anthropic-compatible Messages)."""

from typing import Any

from providers.anthropic_messages import AnthropicMessagesTransport
from providers.base import ProviderConfig
from providers.defaults import WAFER_DEFAULT_BASE


class WaferProvider(AnthropicMessagesTransport):
    """Wafer using ``https://pass.wafer.ai/v1/messages``."""

    def __init__(self, config: ProviderConfig):
        super().__init__(
            config,
            provider_name="WAFER",
            default_base_url=WAFER_DEFAULT_BASE,
        )

    def _build_request_body(
        self, request: Any, thinking_enabled: bool | None = None
    ) -> dict:
        """Build native body; Wafer rejects omitted thinking as ``reasoning_effort=none``."""
        body = super()._build_request_body(request, thinking_enabled=thinking_enabled)
        if "thinking" not in body:
            body["thinking"] = {"type": "enabled"}
        return body

    def _model_list_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}
