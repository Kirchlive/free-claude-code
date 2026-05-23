# Deferred architecture milestones

Work intentionally **not** bundled with the consolidated roadmap implementation. Track these as separate issues or release milestones.

| Item | Reference |
|------|-----------|
| Native Anthropic HTTP adapter collapse | Partial — LM Studio / llama.cpp share [`catalog_thin_native_messages.py`](../../providers/catalog_thin_native_messages.py); further Phase 3b deltas in [native_anthropic_http_providers.md](../../providers/notes/native_anthropic_http_providers.md) / IMPROVEMENT_PLAN |
| Observability port (trace backend abstraction) | Pluggable sink [`core/observability.py`](../../core/observability.py) + [`core/trace.py`](../../core/trace.py). `STRUCTURED_TRACE_SINK` (`default` / `noop` / `otlp_http`) wired by [`api/trace_sink.py`](../../api/trace_sink.py). OTLP uses [`api/telemetry_otlp.py`](../../api/telemetry_otlp.py) with optional-deps `observability` (`uv sync --extra observability`). Sampling / richer span modeling still backlog. |
| Global exception handlers + settings | Mitigated — [`api/app.py`](../../api/app.py) exception handlers call explicit [`get_settings()`](../../config/settings.py): `Depends(get_settings)` is not relied on inside those globals. FastAPI quirks remain vendor-side only. |
| Packaging `smoke` in the wheel | Intentionally dev-only per IMPROVEMENT_PLAN |
| Further slim `config/settings.py` | Mixins + [`settings_coherence_mixins.py`](../../config/settings_coherence_mixins.py); additional thin-down is optional (see [STATUS.md](STATUS.md)) |
| CI path-filtered jobs for `smoke/` | Smoke is manual / opt‑in today—if `smoke/` joins required CI gates, revisit **paths**/job matrices so unrelated PRs skip heavy suites ([GitHub workflows paths](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)). |
| `PlatformOutbound` protocol (messaging) | Done — [`messaging/platforms/outbound.py`](../../messaging/platforms/outbound.py); see [messaging.md](messaging.md). |
