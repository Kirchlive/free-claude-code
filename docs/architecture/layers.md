# Package layers

This repo is a layered Python layout. **Imports are enforced by** `tests/contracts/test_import_boundaries.py` — refactors must keep those tests green.

## Packages

| Package | Role |
|---------|------|
| `config` | Environment and provider catalog (`Settings`, `provider_catalog`). Must not import `api`, `messaging`, `cli`, `providers`, or `core`. |
| `core` | Neutral Anthropic protocol, SSE, and conversion helpers. Must not import product packages (`api`, `messaging`, `cli`, `providers`, `config`, `smoke`). |
| `providers` | Upstream adapters and `ProviderRegistry`. Must not import `api`, `messaging`, or `cli`. |
| `api` | FastHTTP layer, admin UI, orchestration wiring orientation: [api-package.md](api-package.md). Must only import a **narrow** `providers` facade (see contract test `_API_ALLOWED_PROVIDER_MODULES`). |
| `messaging` | Optional Discord/Telegram runtime. Wired from `AppRuntime`; must not import `api` or `cli`. Only `providers.nvidia_nim.transcription_backend` may be imported (`_MESSAGING_ALLOWED_PROVIDER_MODULES`). |
| `cli` | Entry points (`fcc-server`, etc.). May import only `api.app` / `api.admin_urls` plus non-API packages. |

## Provider resolution

1. **HTTP requests:** Use `resolve_provider(provider_type, app=request.app, settings=...)` from `api.dependencies`. The app-mounted `ProviderRegistry` lives at `app.state.provider_registry` after `AppRuntime.startup`.

2. **Scripts / unit tests without an app:** Use `get_process_cached_provider*` (legacy aliases still export `get_provider` / `get_provider_for_type`) backed by `api.provider_process_cache.PROCESS_PROVIDERS`.

3. After admin **Apply** or CLI init touching env: call `reload_settings()` from `config.settings` so cached settings refresh (`api/admin_routes.py`, `cli/entrypoints.py`, `smoke/lib/config.py` follow this invariant).

Shared Anthropic shaping belongs in **`core/anthropic`**, not in cross-importing provider `request.py` modules.

## Dual-registry semantics

Two resolution contexts share the same provider identity map (`ProviderRegistry`) but different backing caches:

| Context | Mechanism | When |
|---------|-----------|------|
| **HTTP / ASGI** | `resolve_provider(provider_type, app=request.app, settings=...)`. Uses `request.app.state.provider_registry` wired by **`AppRuntime` startup**. | Production and tests that mount the full lifespan or set `provider_registry` explicitly. Admin **Apply** should rotate registry and reload settings (`reload_settings()`). |
| **No HTTP app** | `resolve_provider(..., app=None, settings=...)`, backed by `api.provider_process_cache.PROCESS_PROVIDERS` wrapped in `ProviderRegistry`. | Scripts, smoke harness helpers, isolated unit scenarios. |

**Bare `FastAPI()`** stacks must set `app.state.provider_registry` when exercising route handlers that fetch providers—or use `app=None` intentionally for process cache only.

Unknown provider IDs and resolution-time auth semantics should behave consistently; **`tests/contracts/test_provider_resolution_semantics.py`** complements import-only contracts.

**HTTP errors:** ingress failures from [`api.dependencies`](../../api/dependencies.py) (subclasses of [`IngressDetailError`](../../api/ingress/errors.py); stable shim [`api.ingress_errors`](../../api/ingress_errors.py)) are rendered as FastAPI-compatible `{"detail": ...}` via [`api.ingress_handlers.register_ingress_exception_handlers`](../../api/ingress/handlers.py) (shim [`api.ingress_handlers`](../../api/ingress_handlers.py)). [`ProviderError`](../../providers/exceptions.py) responses use Anthropic-shaped JSON from [`api.app.create_app`](../../api/app.py). Details: [api-package.md — HTTP error shapes](api-package.md#http-error-shapes).

For where to add HTTP-layer code versus pipelines, see **`docs/architecture/api-package.md`**.

## Logging stacks

| Source | Prefer |
|--------|--------|
| Application flow, correlated request logs | **`loguru`** (including structured events via **`core/trace.py`**). |
| Framework-owned adapters (same stream uvicorn configures) | **`stdlib.logging`** only where bridging into the server logger is unavoidable. |

**`loguru`** remains the structured default; stdlib **`logging`** appears intentionally for uvicorn-controlled surfaces (example: Admin UI banner). Do not sprinkle `logging.getLogger` in domain/protocol code (`core`, `providers`) without a deliberate reason documented next to the call.

Rolling checklist: [`STATUS.md`](STATUS.md).

