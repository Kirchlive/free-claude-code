"""Bundled HTTP server/runtime fields from :class:`~config.settings.Settings`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ServerRuntimeSettings(BaseModel):
    """Server bind + auth knobs (composed for clarity; not standalone env-loaded)."""

    model_config = ConfigDict(frozen=True)

    host: str
    port: int
    anthropic_auth_token: str


class ProviderThroughputSettings(BaseModel):
    """Provider-side rate-limit and concurrency (mirrors ProviderConfig inputs)."""

    model_config = ConfigDict(frozen=True)

    provider_rate_limit: int
    provider_rate_window: int
    provider_max_concurrency: int
