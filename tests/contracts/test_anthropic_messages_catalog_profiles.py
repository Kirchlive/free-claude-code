"""Freeze native Anthropic HTTP catalog fingerprints (`PROVIDER_CATALOG`).

Phase 3b uses these rows to avoid silent drift between docs and descriptors.
"""

from __future__ import annotations

from typing import Any

from config.provider_catalog import PROVIDER_CATALOG


def test_native_transport_catalog_profiles_match_phase3_inventory() -> None:
    """Headers + SSE chunk grouping for first-party Anthropic adapters stay aligned."""

    def row(pid: str) -> tuple[Any, Any, Any, Any]:
        desc = PROVIDER_CATALOG[pid]
        profile = getattr(desc, "native_messages_header_profile", None)
        mode = getattr(desc, "native_stream_chunk_mode", None)
        transport = getattr(desc, "transport_type", None)
        caps = getattr(desc, "capabilities", ())
        caps_t = caps if isinstance(caps, tuple) else ()
        native = "native_anthropic" in caps_t if caps_t else False
        transport_match = transport == "anthropic_messages"
        return (native, transport_match, profile, mode)

    assert row("open_router") == (
        True,
        True,
        "anthropic_bearer_sse",
        "event",
    )
    assert row("deepseek") == (
        True,
        True,
        "anthropic_x_api_key_sse",
        None,
    )
    assert row("lmstudio") == (
        True,
        True,
        "messages_minimal",
        "line",
    )
    assert row("llamacpp") == (
        True,
        True,
        "messages_minimal",
        "line",
    )
    assert row("ollama") == (
        True,
        True,
        "messages_minimal",
        "line",
    )
    assert row("wafer") == (
        True,
        True,
        "anthropic_bearer_sse",
        None,
    )
