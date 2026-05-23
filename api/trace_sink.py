"""Wire structured trace dispatch from typed settings (:mod:`core` stays config-free).

``core.observability`` exposes :func:`~core.observability.set_trace_dispatch`; this module
consumes typed settings exposing ``structured_trace_sink`` (:class:`~config.settings.Settings`).
"""

from __future__ import annotations

from typing import Any, Protocol

from config.observability_settings import StructuredTraceSink
from core.observability import set_trace_dispatch


class StructuredTraceSinkSource(Protocol):
    structured_trace_sink: StructuredTraceSink


def reset_structured_trace_settings() -> None:
    """Restore built-in structured trace emission (clear any custom dispatch)."""

    set_trace_dispatch(None)


def apply_structured_trace_settings(settings: StructuredTraceSinkSource) -> None:
    """Install ``noop`` suppression or revert to defaults per ``structured_trace_sink``."""

    mode: StructuredTraceSink = settings.structured_trace_sink
    if mode == "noop":

        def _discard(_payload: dict[str, Any]) -> None:
            return None

        set_trace_dispatch(_discard)
        return
    if mode != "default":
        msg = f"unknown structured_trace_sink: {mode!r}"
        raise ValueError(msg)
    set_trace_dispatch(None)
