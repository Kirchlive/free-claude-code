# Native Anthropic HTTP transport (`AnthropicMessagesTransport`) deltas

This note inventories first-party-style providers that inherit
`AnthropicMessagesTransport` (:mod:`providers.anthropic_messages` façade →
:class:`~providers.anthropic_messages_transport.AnthropicMessagesTransport`). The goal
is to **dedupe deltas** (headers, `stream_chunk_mode`, request body builders, and
sanitize hooks) using small strategy modules or catalog flags alongside the shared
**`httpx` + SSE** pipeline (`core/anthropic`).

## Subclasses (manual `httpx` streaming)

| Adapter | Module | Typical stream / body notes |
| --- | --- | --- |
| `LmStudioProvider` | `providers/lmstudio/client.py` | Local LM Studio native messages |
| `LlamaCppProvider` | `providers/llamacpp/client.py` | llama.cpp server compatibility |
| `OllamaProvider` | `providers/ollama/client.py` | Ollama native `/v1/messages` quirks |
| `OpenRouterProvider` | `providers/open_router/client.py` | `stream_chunk_mode="event"` tier |
| `DeepSeekProvider` | `providers/deepseek/client.py` | Request sanitization (`deepseek/request`) |
| `WaferProvider` | `providers/wafer/client.py` | Hosted Anthropic-compat endpoint |

Keep OpenAI-chat gateways (`AsyncOpenAI` + SSE conversion) **separate**: they do
not use this inheritance chain.

## Catalog strategy matrix (Phase 3b inventory)

Frozen view of **`PROVIDER_CATALOG`** fields that already drive native HTTP behavior
(headers + SSE chunk grouping). Use this table before adding new subclasses; extend
[**`config.provider_catalog`**](../../config/provider_catalog.py) rows instead of duplicating deltas in code where possible.

| `provider_id` | `native_stream_chunk_mode` | `native_messages_header_profile` | Subclass deltas (beyond transport base) |
| --- | --- | --- | --- |
| `open_router` | `event` | `anthropic_bearer_sse` | `OpenRouter`: event-mode SSE transforms, bespoke model list + request body [`open_router/request.py`](../../providers/open_router/request.py) |
| `deepseek` | (default `line`) | `anthropic_x_api_key_sse` | Custom model-list URL; body via [`deepseek/request.py`](../../providers/deepseek/request.py) |
| `lmstudio` | `line` | `messages_minimal` | Thin shell (default URL + registry id only) |
| `llamacpp` | `line` | `messages_minimal` | Thin shell (distinct default URL / credential static) |
| `ollama` | `line` | `messages_minimal` | Custom `_send_stream_request` + model list path |
| `wafer` | (default `line`) | `anthropic_bearer_sse` | Default body injects ``thinking``; bearer model-list |

**Collapse candidates:** `lmstudio` and `llamacpp` share the same catalog fingerprints
today—eligible for one catalog-bound factory partial once regression tests exist for both.

### Golden / regression checklist (manual until automated matrix lands)

Run native transport / conversion tests (`tests/providers/test_*` for adapters above plus
SSE golden suites if present) whenever changing shared transport or catalog defaults.

---

## Implementation notes (prior art)

1. Prefer **explicit per-`provider_id` strategy structs** next to catalog entries over
   one-off subclass branches when differences are headers or stream flags only.
2. Never cross-import adapter `*_request.py` modules from each other—shared shaping
   belongs in **`core/anthropic`** builders (`AGENTS.md`).
