"""Bundled messaging settings derived from :class:`~config.settings.Settings`.

These are composed on the primary settings object for dependency injection without
calling :func:`~config.settings.get_settings` from messaging internals.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MessagingSettings(BaseModel):
    """Stable slice of messaging-related flags (not independently env-loaded)."""

    model_config = ConfigDict(frozen=True)

    messaging_platform: str
    messaging_rate_limit: int
    messaging_rate_window: float
    log_messaging_error_details: bool
    log_raw_messaging_content: bool
