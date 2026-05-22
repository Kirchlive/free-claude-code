import {
  Callout,
  CollapsibleSection,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  computeDAGLayout,
  useHostTheme,
} from 'cursor/canvas';

const ENTITIES: Array<[string, string, string, string]> = [
  ['config', 'Settings, ProviderCatalog, NimSettings, paths', 'Env, model mappings, credentials', 'api, providers, messaging'],
  ['cli', 'entrypoints, CLISessionManager, CLISession, process_registry', 'fcc-server / fcc-claude / fcc-init', 'messaging (via protocol)'],
  ['api / server', 'FastAPI app, AppRuntime, routes, dependencies', 'HTTP gateway, lifespan, auth', 'providers.registry (narrow)'],
  ['request', 'MessagesRequest, TokenCountRequest, native_messages_request', 'Anthropic-shaped inbound payloads', 'proxy service, providers'],
  ['proxy service', 'ClaudeProxyService', 'Orchestrates route → optimize → route model → stream', 'model router, registry, core'],
  ['model router', 'ModelRouter, gateway_model_ids', 'Claude model id → provider + upstream model', 'config settings'],
  ['optimizations', 'detection + optimization_handlers', 'Short-circuit quota/title/suggestion probes', 'proxy service (before provider)'],
  ['core / anthropic', 'SSE, conversion, tokens, errors, stream_contracts, thinking', 'Protocol-neutral Anthropic logic', 'providers (never api/messaging)'],
  ['provider registry', 'ProviderRegistry, factories, descriptors', 'Lazy-create/cache providers, model list refresh', 'api.dependencies'],
  ['provider', 'BaseProvider, ProviderConfig, 11 adapters', 'Upstream HTTP + stream translation', 'core, GlobalRateLimiter'],
  ['transports', 'AnthropicMessagesTransport, OpenAIChatTransport', 'Shared streaming paths per upstream API shape', 'provider adapters'],
  ['rate limiter (API)', 'GlobalRateLimiter + StrictSlidingWindowLimiter', 'Proactive throttle + reactive 429/5xx backoff + concurrency', 'all provider streams'],
  ['rate limiter (messaging)', 'MessagingRateLimiter', 'Outgoing platform API throttle + dedupe queue', 'Telegram / Discord sends'],
  ['messaging', 'ClaudeMessageHandler, SessionStore, TreeQueueManager', 'Bot sessions, reply trees, CLI event pipeline', 'platforms, cli manager'],
  ['platforms', 'TelegramPlatform, DiscordPlatform (MessagingPlatform)', 'Inbound messages, outbound edits', 'messaging limiter'],
  ['admin', 'admin_routes, admin_config', 'Loopback /admin UI, validate/apply .env', 'config, registry probe'],
  ['web tools', 'web_tools (egress, parsers, streaming)', 'Claude server-tool fetch/search passthrough', 'proxy service'],
  ['trace', 'trace_event, session id extraction', 'Structured diagnostics across layers', 'api, providers, messaging'],
];

/** Runtime entities omitted from the first pass (tests/smoke excluded). */
const MISSED_ENTITIES: Array<[string, string, string, string]> = [
  ['server.py', 'create_asgi_app() shim', 'Uvicorn `server:app` entry (parallel to fcc-server)', 'api.app'],
  ['GracefulLifespanApp', 'ASGI lifespan wrapper', 'Suppresses Starlette tracebacks on startup failure', 'FastAPI app'],
  ['auth', 'require_api_key (dependencies)', 'Optional ANTHROPIC_AUTH_TOKEN gate on routes', 'Settings'],
  ['dependencies cache', '_providers dict + cleanup_provider', 'Process-level provider cache (non-HTTP callers)', 'ProviderRegistry'],
  ['detection', 'api/detection.py', 'Classify probe requests (quota, title, prefix, filepath)', 'MessagesRequest'],
  ['command_utils', 'extract_command_prefix, extract_filepaths', 'CLI command parsing for mocks', 'optimizations'],
  ['validation_log', 'summarize_request_validation_body', '422 body logging for FastAPI validation', 'app exception handler'],
  ['response DTOs', 'MessagesResponse, TokenCountResponse, Usage, ModelResponse', 'Outbound Anthropic-shaped payloads', 'routes, proxy service'],
  ['routing VOs', 'ResolvedModel, RoutedMessagesRequest, DecodedGatewayModelId', 'Post-route request + model metadata', 'ModelRouter'],
  ['upstream request builders', '*/request.py per adapter (NIM, DeepSeek, OR, …)', 'Provider-specific outbound body build/sanitize', 'MessagesRequest, core conversion'],
  ['error_mapping', 'map_error, ProviderError hierarchy', 'Upstream failures → typed provider errors', 'transports'],
  ['model listing', 'ProviderModelInfo, extract_*_model_ids', 'Parse /v1/models upstream responses', 'ProviderRegistry refresh'],
  ['registry helpers', 'build_provider_config, create_provider', 'Descriptor → ProviderConfig → factory', 'ProviderCatalog'],
  ['providers.defaults', 'URL constant re-exports', 'Adapter default base URLs from catalog', 'config.provider_catalog'],
  ['AnthropicToOpenAIConverter', 'core/anthropic/conversion/*', 'Messages → OpenAI chat body (+ golden fixtures)', 'OpenAIChatTransport'],
  ['SSE pipeline', 'SSEBuilder, ContentBlockManager, HeuristicToolParser', 'OpenAI chunk → Anthropic SSE', 'OpenAIChatTransport'],
  ['native SSE policy', 'EmittedNativeSseTracker, NativeSseBlockPolicyState', 'Native upstream SSE normalization', 'AnthropicMessagesTransport'],
  ['provider_stream_error', 'iter_provider_stream_error_sse_events', 'Error events as SSE on stream failure', 'transports'],
  ['stream_contracts', 'SSEEvent, assert_anthropic_stream_contract', 'Parse/validate SSE event sequences', 'core consumers'],
  ['content helpers', 'extract_text_from_content, get_block_attr', 'Block traversal utilities', 'detection, messaging'],
  ['server_tool_sse', 'core/anthropic/server_tool_sse.py', 'Server-tool block SSE helpers', 'web_tools streaming'],
  ['ConfiguredChatModelRef', 'config/settings per-model refs', 'Opus/Sonnet/Haiku → provider+model mapping', 'ModelRouter'],
  ['config.constants / paths', 'HTTP timeouts, token caps, config_dir, managed .env', 'Shared literals and filesystem layout', 'Settings, logging'],
  ['logging_config', 'configure_logging, InterceptHandler', 'stdlib → loguru bridge, redaction', 'app startup'],
  ['ClaudeCliConfig + CLISession', 'cli/session.py', 'Single subprocess + stream-json parser', 'CLISessionManager'],
  ['process_registry', 'register_pid, kill_pid_tree_best_effort', 'Track/orphan-kill CLI children on shutdown', 'fcc-server, server.py'],
  ['IncomingMessage', 'messaging/models.py', 'Platform inbound DTO', 'platforms → handler'],
  ['platform factory', 'create_messaging_platform, MessagingPlatformOptions, nim transcription inject', 'Runtime composes backends; messaging stays import-clean', 'AppRuntime'],
  ['CLI protocols', 'CLISession, SessionManagerInterface', 'Decouple messaging from cli package imports', 'handler, platforms.base'],
  ['event pipeline', 'event_parser, node_event_pipeline, cli_event_constants', 'CLI JSON events → handler actions', 'handler'],
  ['incoming turn', 'incoming_turn.dispatch_incoming_user_message', 'Splits handler ingress from tree enqueue wiring', 'ClaudeMessageHandler'],
  ['bot commands', 'command_dispatcher, commands (/stop /stats /clear)', 'Slash-command routing', 'handler'],
  ['transcript', 'transcript_segments, transcript_buffer, ThrottledTranscriptEditor', 'Ordered live transcript + throttled edits', 'handler, RenderingProfile'],
  ['rendering', 'RenderingProfile, telegram/discord markdown, markdown_tables', 'Platform-specific markdown/status formatting', 'platforms'],
  ['voice / ASR', 'VoiceTranscriptionService, TranscriptionBackend, transcription.py', 'Voice notes → text (Whisper local or NIM via factory)', 'platforms, handler'],
  ['tree internals', 'TreeRepository, TreeQueueProcessor, MessageNode/Tree/State', 'Per-thread queue, node lifecycle', 'TreeQueueManager'],
  ['safe_diagnostics', 'format_exception_for_log', 'Redacted exception logging for messaging', 'limiter, handler'],
  [
    'discoverability',
    'README Architecture + MISSED_entities',
    'Architecture prose + canvas labels track imports after structural PRs',
    'contract suites',
  ],
  [
    'catalog hygiene',
    'PROVIDER_CATALOG + registry factories + native profiles',
    'New adapter: descriptor, registry wiring, contracts, README/canvas touch-in',
    'tests/contracts',
  ],
];

const DAG_NODES = [
  { id: 'config' },
  { id: 'claude-client' },
  { id: 'bot-user' },
  { id: 'fcc-server' },
  { id: 'api-runtime' },
  { id: 'routes' },
  { id: 'proxy-svc' },
  { id: 'model-router' },
  { id: 'optimizations' },
  { id: 'request-models' },
  { id: 'core-protocol' },
  { id: 'registry' },
  { id: 'provider' },
  { id: 'global-rl' },
  { id: 'upstream' },
  { id: 'platform' },
  { id: 'msg-handler' },
  { id: 'msg-rl' },
  { id: 'cli-mgr' },
  { id: 'claude-subproc' },
];

const DAG_EDGES = [
  { from: 'config', to: 'api-runtime' },
  { from: 'config', to: 'model-router' },
  { from: 'config', to: 'registry' },
  { from: 'fcc-server', to: 'api-runtime' },
  { from: 'api-runtime', to: 'routes' },
  { from: 'api-runtime', to: 'platform' },
  { from: 'claude-client', to: 'routes' },
  { from: 'bot-user', to: 'platform' },
  { from: 'routes', to: 'proxy-svc' },
  { from: 'routes', to: 'request-models' },
  { from: 'proxy-svc', to: 'model-router' },
  { from: 'proxy-svc', to: 'optimizations' },
  { from: 'proxy-svc', to: 'registry' },
  { from: 'proxy-svc', to: 'core-protocol' },
  { from: 'model-router', to: 'config' },
  { from: 'registry', to: 'provider' },
  { from: 'provider', to: 'core-protocol' },
  { from: 'provider', to: 'global-rl' },
  { from: 'global-rl', to: 'upstream' },
  { from: 'platform', to: 'msg-handler' },
  { from: 'msg-handler', to: 'cli-mgr' },
  { from: 'msg-handler', to: 'msg-rl' },
  { from: 'msg-rl', to: 'platform' },
  { from: 'cli-mgr', to: 'claude-subproc' },
  { from: 'claude-subproc', to: 'routes' },
];

const NODE_LABELS: Record<string, string> = {
  config: 'config',
  'claude-client': 'Claude Code',
  'bot-user': 'Discord / TG',
  'fcc-server': 'fcc-server',
  'api-runtime': 'AppRuntime',
  routes: 'routes',
  'proxy-svc': 'ClaudeProxyService',
  'model-router': 'ModelRouter',
  optimizations: 'optimizations',
  'request-models': 'MessagesRequest',
  'core-protocol': 'core/anthropic',
  registry: 'ProviderRegistry',
  provider: 'BaseProvider',
  'global-rl': 'GlobalRateLimiter',
  upstream: 'upstream APIs',
  platform: 'MessagingPlatform',
  'msg-handler': 'ClaudeMessageHandler',
  'msg-rl': 'MessagingRateLimiter',
  'cli-mgr': 'CLISessionManager',
  'claude-subproc': 'claude subprocess',
};

function ArchitectureDiagram() {
  const theme = useHostTheme();
  const layout = computeDAGLayout({
    nodes: DAG_NODES,
    edges: DAG_EDGES,
    direction: 'vertical',
    nodeWidth: 148,
    nodeHeight: 36,
    rankGap: 56,
    nodeGap: 20,
    padding: 28,
  });

  const nodeById = Object.fromEntries(layout.nodes.map((n) => [n.id, n]));
  const fill = theme.bg.elevated;
  const stroke = theme.stroke.secondary;
  const textFill = theme.text.primary;
  const accent = theme.accent.primary;
  const backStroke = theme.text.tertiary;

  return (
    <svg
      width={layout.width}
      height={layout.height}
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      role="img"
      aria-label="Entity interaction diagram for free-claude-code"
    >
      {layout.edges.map((edge) => {
        const dash = edge.isBackEdge ? '6 4' : undefined;
        const color = edge.isBackEdge ? backStroke : stroke;
        return (
          <line
            key={`${edge.from}-${edge.to}`}
            x1={edge.sourceX}
            y1={edge.sourceY}
            x2={edge.targetX}
            y2={edge.targetY}
            stroke={color}
            strokeWidth={edge.isBackEdge ? 1 : 1.25}
            strokeDasharray={dash}
            markerEnd="url(#arrow)"
          />
        );
      })}
      <defs>
        <marker
          id="arrow"
          markerWidth="8"
          markerHeight="8"
          refX="6"
          refY="4"
          orient="auto"
        >
          <path d="M0,0 L8,4 L0,8 Z" fill={stroke} />
        </marker>
      </defs>
      {layout.nodes.map((node) => {
        const isCore = node.id === 'core-protocol' || node.id === 'config';
        return (
          <g key={node.id}>
            <rect
              x={node.x}
              y={node.y}
              width={148}
              height={36}
              rx={6}
              fill={fill}
              stroke={isCore ? accent : stroke}
              strokeWidth={isCore ? 1.5 : 1}
            />
            <text
              x={node.x + 74}
              y={node.y + 22}
              textAnchor="middle"
              fill={textFill}
              fontSize={11}
              fontFamily="ui-monospace, monospace"
            >
              {NODE_LABELS[node.id] ?? node.id}
            </text>
          </g>
        );
      })}
      {/* highlight feedback loop */}
      {(() => {
        const from = nodeById['claude-subproc'];
        const to = nodeById['routes'];
        if (!from || !to) return null;
        return (
          <text
            x={(from.x + to.x) / 2 + 74}
            y={Math.min(from.y, to.y) - 6}
            textAnchor="middle"
            fill={theme.text.secondary}
            fontSize={10}
          >
            Anthropic HTTP back to proxy
          </text>
        );
      })()}
    </svg>
  );
}

export default function EntityArchitectureMap() {
  return (
    <Stack gap={24}>
      <Stack gap={6}>
        <H1>Entity map: free-claude-code</H1>
        <Text tone="secondary" size="small">
          All major runtime entities and how they interact. Solid arrows are
          primary call/data flow; dashed edges (if any) are cycle back-edges
          detected by layout.
        </Text>
        <Text tone="secondary" size="small">
          Source: static codebase analysis · 2026-05-22
        </Text>
      </Stack>

      <Grid columns={4} gap={14}>
        <Stat value="7" label="First-party packages" />
        <Stat value="11" label="Provider adapters" />
        <Stat value="2" label="Rate limiters" tone="warning" />
        <Stat value="2" label="Request paths" />
      </Grid>

      <Callout title="Two request paths" tone="neutral">
        <Text>
          <Text weight="medium">Proxy path</Text> — Claude Code (or any Anthropic
          client) hits FastAPI routes → ClaudeProxyService → ModelRouter →
          ProviderRegistry → BaseProvider → GlobalRateLimiter → upstream.
        </Text>
        <Text>
          <Text weight="medium">Messaging path</Text> — Discord/Telegram →
          platform → ClaudeMessageHandler → CLISessionManager spawns a real
          claude subprocess that calls the same proxy routes. Outbound platform
          edits go through MessagingRateLimiter.
        </Text>
      </Callout>

      <Divider />

      <H2>Interaction diagram</H2>
      <Text tone="secondary" size="small">
        Top-to-bottom: typical dependency and request direction. config and
        core/anthropic are highlighted (neutral shared layers).
      </Text>
      <ArchitectureDiagram />

      <Divider />

      <H2>Entity inventory by layer</H2>
      <Table
        headers={['Layer / package', 'Key types & modules', 'Responsibility', 'Depends on']}
        rows={ENTITIES}
      />

      <Divider />

      <H2>Previously missed (runtime only)</H2>
      <Text tone="secondary" size="small">
        Second pass — granular modules and value objects not called out in the
        first table. Tests and smoke tiers excluded.
      </Text>
      <Table
        headers={['Entity', 'Location', 'Role', 'Used by']}
        rows={MISSED_ENTITIES}
      />

      <Divider />

      <CollapsibleSection title="Entities you named — plus neighbors">
        <Stack gap={10}>
          <Row gap={12}>
            <Text weight="medium" style={{ minWidth: 120 }}>
              CLI
            </Text>
            <Text>
              fcc-server starts Uvicorn; fcc-claude wraps the real claude binary
              with proxy env vars. CLISessionManager owns subprocess pools for
              messaging.
            </Text>
          </Row>
          <Row gap={12}>
            <Text weight="medium" style={{ minWidth: 120 }}>
              Server
            </Text>
            <Text>
              FastAPI app + AppRuntime lifecycle. routes expose /v1/messages,
              /v1/models, /health; admin_routes are loopback-only.
            </Text>
          </Row>
          <Row gap={12}>
            <Text weight="medium" style={{ minWidth: 120 }}>
              Request
            </Text>
            <Text>
              api/models/anthropic (Pydantic inbound). Providers may clone/build
              native_messages_request or OpenAI chat bodies per adapter.
            </Text>
          </Row>
          <Row gap={12}>
            <Text weight="medium" style={{ minWidth: 120 }}>
              Provider
            </Text>
            <Text>
              BaseProvider + registry factories. Transports split:
              AnthropicMessagesTransport vs OpenAIChatTransport (NIM, Z.ai, …).
            </Text>
          </Row>
          <Row gap={12}>
            <Text weight="medium" style={{ minWidth: 120 }}>
              Rate limiter
            </Text>
            <Text>
              GlobalRateLimiter (providers/rate_limit) for upstream API;
              MessagingRateLimiter for platform outbound; shared
              StrictSlidingWindowLimiter in core/rate_limit.
            </Text>
          </Row>
          <Row gap={12}>
            <Text weight="medium" style={{ minWidth: 120 }}>
              Also
            </Text>
            <Text>
              See “Previously missed” table: detection, upstream request
              builders, SSE/conversion pipeline, transcript/voice (TranscriptionBackend),
              tree internals, auth, dual provider cache, server.py shim.
            </Text>
          </Row>
        </Stack>
      </CollapsibleSection>

      <Divider />

      <H2>Enforced layer rules (use for refactors)</H2>
      <Grid columns={2} gap={16}>
        <Stack gap={8}>
          <H3>Allowed dependency direction</H3>
          <Text size="small">
            config → anything (no imports from product code)
          </Text>
          <Text size="small">
            core → nothing product-specific
          </Text>
          <Text size="small">
            providers → core, config (not api / messaging / cli)
          </Text>
          <Text size="small">
            api → providers facade only (registry, base, exceptions)
          </Text>
          <Text size="small">
            messaging → platforms + trees; no static providers.* imports
          </Text>
          <Text size="small">
            cli → api + config for entrypoints
          </Text>
        </Stack>
        <Stack gap={8}>
          <H3>Principles to improve</H3>
          <Text size="small">
            Single owner for provider lifecycle (app.state.registry vs legacy
            cache in dependencies)
          </Text>
          <Text size="small">
            Keep protocol logic in core/anthropic; never cross-import adapters
          </Text>
          <Text size="small">
            Provider-specific config stays in adapter constructors, not
            ProviderConfig base
          </Text>
          <Text size="small">
            Split god-modules (admin_config, handler, trees) along entity
            boundaries above
          </Text>
          <Text size="small">
            Two rate limiters are intentional — do not merge; document scopes
          </Text>
        </Stack>
      </Grid>

      <Text tone="secondary" size="small">
        Contract source: tests/contracts/test_import_boundaries.py,
        test_architecture_contracts.py, AGENTS.md
      </Text>
    </Stack>
  );
}
