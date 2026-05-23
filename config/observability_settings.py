"""Logging / diagnostics flags (derived views of :class:`~config.settings.Settings`)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

StructuredTraceSink = Literal["default", "noop"]


class ObservabilitySettings(BaseModel):
    """Bundled verbosity controls for API, SSE, CLI, and messaging."""

    model_config = ConfigDict(frozen=True)

    log_raw_api_payloads: bool
    log_raw_sse_events: bool
    log_api_error_tracebacks: bool
    log_raw_messaging_content: bool
    log_raw_cli_diagnostics: bool
    log_messaging_error_details: bool
    debug_platform_edits: bool
    debug_subagent_stack: bool
    structured_trace_sink: StructuredTraceSink
