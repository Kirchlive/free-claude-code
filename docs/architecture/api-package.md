# The `api` package

Orchestration and HTTP-facing code for the Claude-compatible gateway lives under `api/`. **Import rules** still come from [`tests/contracts/test_import_boundaries.py`](../../tests/contracts/test_import_boundaries.py); this document is orientation only.

## Where to put new code

| Location | Responsibility |
|----------|------------------|
| [`api/routes.py`](../../api/routes.py) | Thin route handlers and shared route-level dependencies (e.g. `get_proxy_service`). Avoid provider construction here; delegate to [`api.dependencies`](../../api.dependencies) and services. |
| [`api/message_create_pipeline.py`](../../api/message_create_pipeline.py) | Ordered steps for **`POST /v1/messages`**: optimizations, web tools branch, upstream streaming. Preserve precedence when extending. |
| [`api/services.py`](../../api/services.py) | `ClaudeProxyService` façade (`create_message`, `count_tokens`). |
| [`api/runtime.py`](../../api/runtime.py) | `AppRuntime` lifecycle: startup/shutdown ordering, registering `provider_registry` on `app.state`. |
| [`api/messaging_startup.py`](../../api/messaging_startup.py) | Messaging stack wired **after** platform bootstrap from `messaging`: CLI session manager, handler, `platform.start()`. Keeps [`messaging/bootstrap.py`](../../messaging/bootstrap.py) free of `cli` imports (import contract). |
| [`api/dependencies.py`](../../api/dependencies.py) | `resolve_provider`, process-cache helpers, `require_api_key`, `get_settings`. |
| [`api/ingress/errors.py`](../../api/ingress/errors.py) (+ stable shim [`api/ingress_errors.py`](../../api/ingress_errors.py)) | Ingress domain errors (resolution + gateway proxy auth) mapped to `{"detail": ...}` by [`api/ingress/handlers.py`](../../api/ingress/handlers.py) (shim [`api/ingress_handlers.py`](../../api/ingress_handlers.py)). |
| [`admin_routes.py`](../../api/admin_routes.py), [`admin/`](../../api/admin/) | Admin UI manifests, persistence, routing. |

## HTTP error shapes

- **Ingress** (before an upstream stream starts): [`api.dependencies`](../../api/dependencies.py)
  raises subclasses of [`IngressDetailError`](../../api/ingress/errors.py) (stable import also
  [`api.ingress_errors.IngressDetailError`](../../api/ingress_errors.py)) (e.g. missing/invalid
  proxy API key, curated provider credential failures while resolving the registry).
  [`register_ingress_exception_handlers`](../../api/ingress/handlers.py) (shim [`api.ingress_handlers`](../../api/ingress_handlers.py)) turns these into
  `JSONResponse` bodies `{"detail": "<message>"}` (401 for gateway auth; 503 for resolution
  auth), matching the legacy `HTTPException` shape. [`ClaudeProxyService`](../../api/services.py)
  re-raises ingress errors instead of translating them into generic 500 responses.
- **Provider / transport**: uncaught [`ProviderError`](../../providers/exceptions.py)
  subclasses use the Anthropic-shaped handler in [`api.app.create_app`](../../api/app.py):
  `{"type": "error", "error": {"type": ..., "message": ...}}`.

## Request flow (internal)

```text
api/routes.py → api/services.py (ClaudeProxyService) → api/message_create_pipeline.py
  → api/dependencies.py (resolve_provider, require_api_key)
```

Admin, web tools, and optimizations branch **before** ``message_create_pipeline`` as documented in the routes table above.

## Provider resolution (`request.app`)

- From route handlers call `resolve_provider(..., app=request.app, settings=settings)` via [`dependencies.resolve_provider`](../../api/dependencies.py). The registry must exist on **`app.state.provider_registry`** after [`AppRuntime.startup`](../../api/runtime.py).

- Scripts, smoke, unit tests **without** a Starlette app use `get_process_cached_provider*` and [`api.provider_process_cache`](../../api/provider_process_cache.py). Do **not** use those shortcuts from **`api.routes`** or **`api.services`**.

See also [layers.md — Provider resolution](layers.md).

## Reloading configuration

After `.env` or environment changes (Admin **Apply**, CLI env init): call **`reload_settings()`** from [`config.settings`](../../config/settings.py) so **`get_settings()`** cache clears. Layers doc lists call sites conceptually.

## Tests and mocks

Patch the **same module attribute the code under test imported**, not necessarily the defining module (`from X import foo` ⇒ patch `unittest.mock.patch("caller_module.foo")`). Example: lifespan tests patch types on [`api.messaging_startup`](../../api/messaging_startup.py) when asserting startup wiring assembled there.

## Related docs

- [layers.md](layers.md) — full layer matrix and dual-registry semantics.
- [messaging.md](messaging.md) — optional bot runtime vs HTTP.
- [admin.md](admin.md) — Admin trust boundary and env split modules.
- [deferred_milestones.md](deferred_milestones.md) — out-of-scope architectural milestones.
- [STATUS.md](STATUS.md) — program checklist vs repo.
