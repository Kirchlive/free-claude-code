# Deferred architecture milestones

Work intentionally **not** bundled with the consolidated roadmap implementation. Track these as separate issues or release milestones.

| Item | Reference |
|------|-----------|
| Native Anthropic HTTP adapter collapse | [providers/notes/native_anthropic_http_providers.md](../../providers/notes/native_anthropic_http_providers.md), IMPROVEMENT_PLAN Phase 3b |
| Observability port (trace backend abstraction) | Pluggable sink [`core/observability.py`](../../core/observability.py) + [`core/trace.py`](../../core/trace.py); `STRUCTURED_TRACE_SINK` (`default`/`noop`) wired from [`api/trace_sink.py`](../../api/trace_sink.py) during [`AppRuntime.startup`](../../api/runtime.py). OTLP / remote backends still backlog. |
| Global exception handlers + settings | Mitigated — [`api/app.py`](../../api/app.py) exception handlers call explicit [`get_settings()`](../../config/settings.py): `Depends(get_settings)` is not relied on inside those globals. FastAPI quirks remain vendor-side only. |
| Packaging `smoke` in the wheel | Intentionally dev-only per IMPROVEMENT_PLAN |
| Further slim `config/settings.py` | Mixins exist; additional thin-down is optional (see [STATUS.md](STATUS.md)) |
| `PlatformOutbound` protocol (messaging) | Done — [`messaging/platforms/outbound.py`](../../messaging/platforms/outbound.py); see [messaging.md](messaging.md). |
