# `api/` module clusters (navigation)

[`api/` package doc](api-package.md) mixes **flat top-level modules** with **focused subfolders** (`admin/`, `ingress/`, `web_tools/`). Until a large-scale move is warranted, treat this doc as **where new code gravitates**.

| Cluster | Typical modules today | Guidance |
|---------|-----------------------|----------|
| **Ingress / resolver** | [`api/ingress/`](../../../api/ingress/), [`api/dependencies.py`](../../../api/dependencies.py) | Prefer [`resolve_provider`](../../../api/dependencies.py) + handlers under `api/ingress/`; extend [`ingress/errors.py`](../../../api/ingress/errors.py) for resolver-shaped failures only. |
| **Runtime / lifespan** | [`api/runtime.py`](../../../api/runtime.py), [`api/runtime_lifecycle.py`](../../../api/runtime_lifecycle.py), [`api/messaging_startup.py`](../../../api/messaging_startup.py) | Composition-only: provider registry, telemetry, messaging stack start; minimal business logic here. |
| **Admin env + persistence** | `api/admin_env_*.py`, [`admin_persistence.py`](../../../api/admin_persistence.py) | Keep read/write symmetry; façade paths stay documented in [`admin.md`](admin.md). |
| **Trace / OTLP shim** | [`trace_sink.py`](../../../api/trace_sink.py), [`telemetry_otlp.py`](../../../api/telemetry_otlp.py) | Optional extras only; OTLP deps stay lazily isolated. |

Future **subpackage extractions** (optional, high-merge-cost): group **`runtime_*`** + **`messaging_startup`** under `api/composition/`; group **`telemetry_*`** + **`trace_sink`** under `api/observability/`—always update Hatch `packages=[...]` implicitly (subfolders stay inside `api/`) and re-run **`tests/contracts/test_import_boundaries.py`**.
