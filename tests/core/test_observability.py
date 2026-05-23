"""Structured trace sink registration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core import observability
from core.trace import trace_event


def test_trace_event_dispatches_via_observability_hook() -> None:
    sink = MagicMock()
    observability.set_trace_dispatch(sink)
    try:
        trace_event(stage="ingress", event="probe.e", source="test", foo=42)
        sink.assert_called_once()
        payload = sink.call_args[0][0]
        assert payload["stage"] == "ingress"
        assert payload["event"] == "probe.e"
        assert payload["source"] == "test"
        assert payload["foo"] == 42
    finally:
        observability.set_trace_dispatch(None)


def test_structured_trace_noop_replaces_active_sink() -> None:
    """``STRUCTURED_TRACE_SINK=noop`` must not forward to a previously installed sink."""

    from types import SimpleNamespace

    from api.trace_sink import (
        apply_structured_trace_settings,
        reset_structured_trace_settings,
    )

    prior = MagicMock()
    observability.set_trace_dispatch(prior)
    prior.reset_mock()
    try:
        apply_structured_trace_settings(SimpleNamespace(structured_trace_sink="noop"))
        trace_event(stage="ingress", event="after.noop", source="test")
        prior.assert_not_called()
    finally:
        reset_structured_trace_settings()


def test_structured_trace_default_restores_builtin_dispatch() -> None:
    """``default`` clears custom dispatch so :func:`dispatch_structured_trace` uses built-ins."""

    from types import SimpleNamespace

    from api.trace_sink import apply_structured_trace_settings

    with patch("api.trace_sink.set_trace_dispatch") as set_dispatch:
        apply_structured_trace_settings(
            SimpleNamespace(structured_trace_sink="default")
        )
    set_dispatch.assert_called_once_with(None)
