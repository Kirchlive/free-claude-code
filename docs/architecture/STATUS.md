# Architecture program status

Snapshot of items from [IMPROVEMENT_PLAN Definition of done](IMPROVEMENT_PLAN.md) and the consolidated roadmap. Update this file when milestones land.

| Criterion | Status | Notes |
|-----------|--------|-------|
| `config/settings.py` composition hub (~290 lines target) | Partial | Mixins in `config/settings_*.py`; validators [`config/settings_validators.py`](../../config/settings_validators.py); bundle builders [`config/settings_bundles.py`](../../config/settings_bundles.py); dotenv guards [`config/settings_env.py`](../../config/settings_env.py); [`config/settings.py`](../../config/settings.py) hub ~326 lines (routing to `settings_*` modules; further slimming optional). |
| `core/anthropic/conversion/_conversion.py` removed | Done | Submodules live under [`core/anthropic/conversion/](../../core/anthropic/conversion/). |
| At least four OpenAI-chat providers use catalog factory | Done | See [`providers/registry_factories.py`](../../providers/registry_factories.py) (`_instantiate_catalog_openai_chat`, catalog-bound partials); re-exported from [`providers/registry.py`](../../providers/registry.py). |
| `api/runtime.py` under ~220 lines; bootstrap in `messaging/bootstrap.py` | Done | Lifecycle helpers [`api/runtime_lifecycle.py`](../../api/runtime_lifecycle.py); [`api/runtime.py`](../../api/runtime.py) ~185 lines. Bootstrap in [`messaging/bootstrap.py`](../../messaging/bootstrap.py). |
| `reload_settings()` at all reload sites | Done | Admin, CLI entrypoints, smoke config (see codebase grep). Tests in [`tests/config/test_config.py`](../../tests/config/test_config.py). |
| `docs/architecture/` layers, provider resolution, messaging | Done | [`layers.md`](layers.md), [`messaging.md`](messaging.md), [`api-package.md`](api-package.md), [`admin.md`](admin.md). |
| `tests/contracts/test_provider_wiring.py` alignment guards | Done | Catalog / admin credential / factories. |
| Import-boundary contract tests green | Maintain | [`tests/contracts/test_import_boundaries.py`](../../tests/contracts/test_import_boundaries.py). |

## Consolidated roadmap (post–IMPROVEMENT_PLAN)

| Track | Purpose |
|-------|---------|
| Transport vs ingress errors | Done | Stable imports [`api/ingress_errors.py`](../../api/ingress_errors.py) → [`api/ingress/errors.py`](../../api/ingress/errors.py); handlers [`api/ingress_handlers.py`](../../api/ingress_handlers.py) → [`api/ingress/handlers.py`](../../api/ingress/handlers.py). Uncaught [`ProviderError`](../../providers/exceptions.py) still uses Anthropic JSON in [`api/app.py`](../../api/app.py). |
| Admin env persistence split | [`api/admin_env_read.py`](../../api/admin_env_read.py), [`api/admin_env_write.py`](../../api/admin_env_write.py), [`api/admin_env_shared.py`](../../api/admin_env_shared.py); stable façade [`api/admin_persistence.py`](../../api/admin_persistence.py). |
| Resolver semantics tests | [`tests/contracts/test_provider_resolution_semantics.py`](../../tests/contracts/test_provider_resolution_semantics.py). |
| Native messages + OpenAI-compat helpers | Inventory [`providers/native_messages_catalog.py`](../../providers/native_messages_catalog.py); [`providers/native_messages_support.py`](../../providers/native_messages_support.py); Phase 3b strategy rollout tracked in [`native_anthropic_http_providers.md`](../../providers/notes/native_anthropic_http_providers.md); tool-arg streaming [`providers/openai_compat_tool_args.py`](../../providers/openai_compat_tool_args.py); factories [`providers/registry_factories.py`](../../providers/registry_factories.py). |
| Messaging outbound protocol | Done | [`PlatformOutbound`](../../messaging/platforms/outbound.py) + [`messaging.md`](messaging.md); handler/command typing uses outbound queue seams. |

**Deferred milestones:** [`deferred_milestones.md`](deferred_milestones.md).
