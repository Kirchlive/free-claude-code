# Architecture (free-claude-code)

This document summarizes how the runtime is layered, where requests enter, and how rate limiting scopes fit together. Principles in [AGENTS.md](../AGENTS.md) remain normative.

## Layered layout

Rough dependency flow:

- **clients** → HTTP API routes or messaging bots.
- **`api`** — FastHTTP surface, Claude proxy orchestration (`ClaudeProxyService`), admin endpoints, lifespan wiring via **`AppRuntime`**.
- **`core`** — Shared protocol/stream/rate-limit math helpers; must not import `api`, `messaging`, `providers`, `config`.
- **`providers`** — Adapter registry, transports toward upstream APIs, provider-scoped `GlobalRateLimiter` instances.
- **`config`** — `Settings`, `provider_catalog`; no imports from runtime layers except neutral env helpers.
- **`messaging`** — Telegram/Discord adapters, Claude CLI session bridge, trees/queue; avoids `api` imports (wired from `api.runtime`).

**Entity map canvas:** [`canvases/entity-architecture-map.canvas.tsx`](../canvases/entity-architecture-map.canvas.tsx) (diagrammatic index of entities and flows).

## Two principal request paths

1. **Anthropic-protocol HTTP** (`/v1/messages`, etc.) via `create_app()` / uvicorn → `ProviderRegistry` on `app.state` → transports.
2. **Messaging bots** → `MessagingPlatform` → `ClaudeMessageHandler` → `CLISessionManager` hitting the local HTTP routes for model calls where applicable.

## Server entrypoints (avoid drifting lifespans)

| Entry | Role |
| ------ | ------ |
| [`server.py`](../server.py) | Imports `create_asgi_app()` and runs uvicorn with `timeout_graceful_shutdown`; installs a process-level subprocess cleanup on `__main__`. |
| **`fcc-server`** ([`cli/entrypoints.py`](../cli/entrypoints.py)) | Packaged CLI that starts the server with similar safeguards and user-facing bootstrap messages. |

Both converge on **`api.app`** ASGI factories and **`AppRuntime`** for lifespan composition (providers, optional messaging, shutdown ordering).

Provider resolution for HTTP should treat **`request.app.state.provider_registry`** as authoritative; **`api.dependencies`** exposes helpers aligned with tests and subprocess-only cache cleanup.

## Catalog as single source for providers

[`config/provider_catalog.py`](../config/provider_catalog.py) defines `PROVIDER_CATALOG`, transport types (`openai_chat` vs `anthropic_messages`), and per-descriptor **`registry_factory`** symbols resolved in [`providers/registry.py`](../providers/registry.py). Routing checks (for example OpenAI-shaped server tooling) derive allowed IDs via **`provider_ids_for_transport`** instead of duplicating literals in **`api`** (see contracts in [`tests/contracts/test_architecture_contracts.py`](../tests/contracts/test_architecture_contracts.py)).

## Messaging diagnostics wiring

Operational flags such as **`log_messaging_error_details`** are injected via **`MessagingPlatformOptions`** (`messaging/platforms/factory.py`) into platform adapters → **`MessagingRateLimiter`**, and into **`TreeQueueProcessor` / `TreeQueueManager`** for queue callback logging. Messaging hot paths avoid calling **`config.settings.get_settings()`** solely for diagnostics.

## Rate limiting (do not unify limiters)

There are three related concepts:

1. **`providers.rate_limit.GlobalRateLimiter` singleton** — Reactive/global coordination (for example mapped errors). Admin hot-reload resets this singleton when the registry is recreated.
2. **`GlobalRateLimiter.get_scoped_instance(...)`** — Per-provider/per-config scoped limiters inside transports so one provider cannot starve another.
3. **`messaging.limiter.MessagingRateLimiter`** — Sliding-window limiter plus compacted asyncio queue for **outbound Telegram/Discord API** calls only (different resource from upstream LLM quotas).

Shut down **`MessagingRateLimiter`** during **`AppRuntime`** shutdown (`_shutdown_limiter`) so asyncio workers exit cleanly alongside provider cleanup.
