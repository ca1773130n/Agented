/**
 * Memory System API — bundled session-memory integrations wired into
 * Agented (per-project knowledge graphs, semantic stores, etc.).
 *
 * Designed to absorb additional memory systems (MemPalace, Cognee,
 * etc.) in the same envelope shape; today, only Tesserae is exposed.
 */

import { apiFetch } from './client';

/**
 * Map a raw backend `reason` token (from `_run_tesserae`: cli_missing / exit_N /
 * timeout_after_Ns / tesserae_disabled / no_paths_to_ingest) to operator-friendly
 * copy. Unknown tokens pass through unchanged (better than nothing). Pass vue-i18n's
 * `t` so the copy is localized.
 */
export function friendlyMemoryReason(
  reason: string | null | undefined,
  t: (key: string) => string,
): string | null {
  if (!reason) return null;
  if (reason === 'cli_missing') return t('memoryCommon.reasonCliMissing');
  if (reason.startsWith('timeout_after_')) return t('memoryCommon.reasonTimeout');
  if (reason.startsWith('exit_')) return t('memoryCommon.reasonExit');
  if (reason === 'tesserae_disabled') return t('memoryCommon.reasonDisabled');
  if (reason === 'no_paths_to_ingest') return t('memoryCommon.reasonNoPaths');
  return reason;
}

export interface MemorySystemCliStatus {
  installed: boolean;
  version: string | null;
  path: string | null;
}

export interface MemorySystemSummary {
  id: string;
  name: string;
  summary: string;
  cli: MemorySystemCliStatus;
  enabled_project_count: number;
}

export interface TesseraeProjectState {
  project_id: string;
  project_name: string;
  local_path: string | null;
  tesserae_project_root: string | null;
  enabled: boolean;
  /** AgentRunbook distillation (Runbook/Gotcha) opt-in for this project. */
  distill_enabled?: boolean;
  workspace_initialized: boolean;
  session_count: number;
  last_imported_at: string | null;
}

export interface TesseraeRefreshResult {
  project_id: string;
  imported: number;
  skipped_reason?: string;
  stdout?: string;
}

export interface TesseraeOpResult {
  op: string;
  ok: boolean;
  stdout?: string;
  stderr?: string;
  reason?: string;
  started_at?: string;
  finished_at?: string;
  elapsed_seconds?: number;
}

export interface TesseraeWorkspaceStatus {
  project_id: string;
  tesserae_root: string | null;
  workspace_initialized: boolean;
  graph_compiled: boolean;
  graph_compiled_at: string | null;
  graph_size_bytes: number | null;
  session_count: number;
  last_session_imported_at: string | null;
  site_built: boolean;
}

export interface TesseraeAsyncJob {
  job_id: string;
  project_id: string;
  op: string;
  status: 'running' | 'completed' | 'failed';
  started_at?: string;
  finished_at?: string;
  result?: TesseraeOpResult;
}

export interface ActivitySummary {
  ok: boolean;
  markdown: string;
  reason: string | null;
}

export interface Decision {
  ts: string;
  source: 'human' | 'agent';
  project: string;
  session_id?: string;
  question: string;
  answer: string;
  options?: string[];
  header?: string;
  rationale?: string;
}

export interface DecisionsResult {
  ok: boolean;
  decisions: Decision[];
  reason: string | null;
}

// Tesserae 0.17 `doctor` — memory-graph health.
export interface DoctorFinding {
  check_id: string;
  category: string;
  severity: 'ok' | 'warn' | 'error' | string;
  message: string;
  suggestion: string | null;
  fixable: boolean;
}

export interface DoctorReport {
  project_root: string;
  checked_at: string;
  exit_code: number;
  fixed: string[];
  findings: DoctorFinding[];
}

export interface DoctorResult {
  ok: boolean;
  report: DoctorReport | null;
  reason: string | null;
}

// Tesserae `config status` — resolved LLM backend + liveness ping.
// Tesserae 0.23/0.24 "sleep cycle" status — sourced from Agented's own
// `engine --all --consolidate` daemon supervisor (the CLI exposes no such field).
export interface ConsolidationStatus {
  enabled: boolean;
  running: boolean;
  idle_seconds: number;
  consolidate_every: number;
  // 0.25 SUMMARIZE op: max LLM calls per tick spent pre-warming community
  // summaries (0 = that op disabled). A real recurring cost, so it is shown.
  summarize_budget?: number;
}

export interface MemoryConfig {
  ok: boolean;
  provider: string | null;
  effort: string | null;
  liveness_ok: boolean | null;
  source: string | null;
  reason: string | null;
  consolidation?: ConsolidationStatus | null;
}

// Tesserae `lint` — graph-QUALITY report (distinct from doctor's operational health).
export interface LintFinding {
  severity: 'info' | 'warning' | 'error' | string;
  code: string;
  message: string;
  node_id: string | null;
  path: string | null;
  suggested_fix: string | null;
  auto_fixable: boolean;
}

export interface LintReport {
  findings: LintFinding[];
  by_code: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface LintResult {
  ok: boolean;
  report: LintReport | null;
  reason: string | null;
}

// Tesserae `status` — compiled knowledge-graph overview.
export interface GraphStatus {
  project: string;
  nodes: number;
  edges: number;
  graph_corrupt: boolean;
  sessions: number;
  last_compile: string | null;
  vault: string | null;
  site: string | null;
}

export interface GraphStatusResult {
  ok: boolean;
  status: GraphStatus | null;
  reason: string | null;
}

// Tesserae `query` — raw BM25/semantic retrieval hits (NO LLM synthesis).
export interface GraphHit {
  title: string;
  kind: string;
  href: string | null;
  score: number;
  excerpt: string | null;
  page_path: string | null;
  node_id: string | null;
  arxiv_id?: string | null;
}

export interface GraphQueryResult {
  ok: boolean;
  question: string;
  hits: GraphHit[];
  reason: string | null;
}

// Tesserae 0.25 `graph-map` — budgeted "Descent" structural navigation. A card is
// a community or node scope; descend via scope_id, ascend via parent_scope, page an
// oversized level via the header cursor.
export interface GraphMapHeader {
  scope: string | null;
  kind: string; // 'root' | 'community' | 'node' | 'agent' | ...
  levels?: number;
  node_count?: number;
  edge_count?: number;
  community_count?: number;
  hubs?: string[];
  total_cards?: number;
  cursor?: number;
}

export interface GraphMapCard {
  scope_id: string;
  kind: string; // 'community' | 'node'
  title: string;
  summary?: string;
  size?: number;
  children_count?: number;
  leaf_member_count?: number;
  parent_scope: string | null;
  tags?: string[];
  quality?: string; // 'llm' | 'structural'
  stale?: boolean;
}

export interface GraphMap {
  header: GraphMapHeader;
  cards: GraphMapCard[];
}

export interface GraphMapResult {
  ok: boolean;
  map: GraphMap | null;
  reason: string | null;
}

// Tesserae `research` — agentic plan→search→reflect→synthesize report (async job).
export interface ResearchResult {
  ok: boolean;
  query: string;
  report_md: string;
  reason: string | null;
}

export interface ResearchJob {
  job_id: string;
  op: string;
  status: 'running' | 'completed' | 'failed';
  started_at?: string;
  finished_at?: string;
  result?: ResearchResult | null;
}

// Tesserae 0.16 `sessions list` — normalized harness session history.
export interface HarnessSession {
  date: string;
  harness: string;
  project: string;
  title: string;
  slug: string;
}

export interface SessionsResult {
  ok: boolean;
  sessions: HarnessSession[];
  reason: string | null;
}

// Tesserae interactive graph explorer — browsable nodes/edges (positions are
// computed in the frontend; the backend emits no coordinates).
export interface GraphNode {
  id: string;
  name: string;
  type: string;
  degree: number;
  center: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  evidence: string | null;
}

export interface GraphOverview {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
  seed: string | null;
}

export interface Subgraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  center: string;
  truncated: boolean;
}

export interface NodeNeighbor {
  id: string;
  name: string;
  type: string;
  edge_type: string;
  direction: string;
}

export interface NodeDetail {
  id: string;
  name: string;
  type: string;
  degree: number;
  description: string | null;
  aliases: string[];
  source_path: string | null;
  neighbors: NodeNeighbor[];
}

// --- Background memory/observability queries (v1) ---
// Any memory/observability query can be dispatched as a background job the
// operator can navigate away from; results land in the query-history store.
export type MemoryQueryKind =
  | 'doctor'
  | 'lint'
  | 'config'
  | 'graph_status'
  | 'activity_summary'
  | 'decisions'
  | 'graph_query'
  | 'sessions'
  | 'research';

// A row in the jobs list (NO result blob — cheap to enumerate).
export interface MemoryJobSummary {
  job_id: string;
  kind: string;
  label: string;
  project_id: string | null;
  status: 'running' | 'completed' | 'failed';
  created_at: string;
  finished_at: string | null;
  error: string | null;
}

// One job WITH its result (the kind-specific payload the old sync endpoint returned).
export interface MemoryJob {
  job_id: string;
  op: string;
  status: 'running' | 'completed' | 'failed';
  started_at?: string;
  finished_at?: string;
  result: unknown;
}

export const memorySystemApi = {
  list: () =>
    apiFetch<{ memory_systems: MemorySystemSummary[] }>(
      '/admin/system/memory',
    ),

  // Daily/weekly "what you did" digest (markdown) via `tesserae summary`.
  // Cached by default; pass refresh=true (the Refresh button) to force a scan.
  activitySummary: (
    period: 'day' | 'week',
    date?: string | null,
    project?: string | null,
    refresh = false,
    maxTurns?: number | null,
  ) => {
    const qs = new URLSearchParams({ period });
    if (date) qs.set('date', date);
    if (project) qs.set('project', project);
    if (maxTurns) qs.set('max_turns', String(maxTurns));
    if (refresh) qs.set('refresh', 'true');
    return apiFetch<ActivitySummary>(`/admin/system/memory/activity-summary?${qs.toString()}`);
  },

  // Human (AskUserQuestion) + agent decisions across projects via `tesserae decisions`.
  decisions: (
    period: 'day' | 'week',
    date?: string | null,
    project?: string | null,
    includeAgent = true,
    refresh = false,
    maxTurns?: number | null,
  ) => {
    const qs = new URLSearchParams({ period, include_agent: String(includeAgent) });
    if (date) qs.set('date', date);
    if (project) qs.set('project', project);
    if (maxTurns) qs.set('max_turns', String(maxTurns));
    if (refresh) qs.set('refresh', 'true');
    return apiFetch<DecisionsResult>(`/admin/system/memory/decisions?${qs.toString()}`);
  },

  // Tesserae 0.17 memory-graph health (init/graph/registry/staleness/locks).
  doctor: (refresh = false) => {
    const qs = refresh ? '?refresh=true' : '';
    return apiFetch<DoctorResult>(`/admin/system/memory/doctor${qs}`);
  },

  // Tesserae `lint` — graph QUALITY (unsupported claims, orphans, wiki drift, staleness).
  lint: (refresh = false) => {
    const qs = refresh ? '?refresh=true' : '';
    return apiFetch<LintResult>(`/admin/system/memory/lint${qs}`);
  },

  // Tesserae `status` — compiled knowledge-graph overview (node/edge/session counts).
  graphStatus: () =>
    apiFetch<GraphStatusResult>('/admin/system/memory/graph/status'),

  // --- Interactive graph explorer (browsable nodes/edges) ---

  // A connected landing subgraph (never empty) + total node/edge counts.
  graphOverview: (project?: string | null, maxNodes = 50) => {
    const qs = new URLSearchParams({ max_nodes: String(maxNodes) });
    if (project) qs.set('project', project);
    return apiFetch<GraphOverview>(`/admin/system/memory/graph/overview?${qs.toString()}`);
  },

  // Ranked node search (name/alias/description) — clickable hits.
  graphSearchNodes: (q: string, project?: string | null, limit = 25) => {
    const qs = new URLSearchParams({ q, limit: String(limit) });
    if (project) qs.set('project', project);
    return apiFetch<{ nodes: GraphNode[] }>(`/admin/system/memory/graph/nodes?${qs.toString()}`);
  },

  // A node's N-hop neighborhood (nodes + connecting edges). nodeId is a query
  // param (ids contain ':'); URLSearchParams URL-encodes it.
  graphSubgraph: (nodeId: string, project?: string | null, hops = 1, maxNodes = 60) => {
    const qs = new URLSearchParams({
      node_id: nodeId,
      hops: String(hops),
      max_nodes: String(maxNodes),
    });
    if (project) qs.set('project', project);
    return apiFetch<Subgraph>(`/admin/system/memory/graph/subgraph?${qs.toString()}`);
  },

  // Full detail for one node: description, aliases, source, typed neighbors.
  graphNodeDetail: (nodeId: string, project?: string | null) => {
    const qs = new URLSearchParams({ node_id: nodeId });
    if (project) qs.set('project', project);
    return apiFetch<NodeDetail>(`/admin/system/memory/graph/node?${qs.toString()}`);
  },

  // Tesserae `query` — raw retrieval search over the knowledge graph (NO LLM).
  graphQuery: (q: string, topK = 8, kind?: string | null) => {
    const qs = new URLSearchParams({ q, top_k: String(topK) });
    if (kind) qs.set('kind', kind);
    return apiFetch<GraphQueryResult>(`/admin/system/memory/graph/query?${qs.toString()}`);
  },

  // Tesserae 0.25 `graph-map` — Descent structural navigation. Omit scope for the
  // root map; pass a card's scope_id to descend, its parent_scope to ascend, cursor
  // to page an oversized level.
  graphMap: (scope?: string | null, cursor = 0, budgetChars?: number | null) => {
    const qs = new URLSearchParams();
    if (scope) qs.set('scope', scope);
    if (cursor) qs.set('cursor', String(cursor));
    if (budgetChars != null) qs.set('budget_chars', String(budgetChars));
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return apiFetch<GraphMapResult>(`/admin/system/memory/graph/map${suffix}`);
  },

  // Tesserae `config status` — resolved LLM backend + liveness ping.
  config: () =>
    apiFetch<MemoryConfig>('/admin/system/memory/config'),

  // Tesserae `engine --all --once` — coalesced recompile drain (async job).
  engineRefresh: () =>
    apiFetch<{ job_id: string; op: string; status: string }>(
      '/admin/system/memory/engine-refresh',
      { method: 'POST' },
    ),

  // Tesserae `research` — kick off the agentic loop (async); poll researchJob(jobId).
  startResearch: (query: string) =>
    apiFetch<{ job_id: string; op: string; status: string }>(
      '/admin/system/memory/research',
      { method: 'POST', body: JSON.stringify({ query }) },
    ),

  // Poll a research job (shares the tesserae jobs store; result carries report_md).
  researchJob: (jobId: string) =>
    apiFetch<ResearchJob>(
      `/admin/system/memory/tesserae/jobs/${encodeURIComponent(jobId)}`,
    ),

  // Tesserae 0.16 normalized harness session history.
  sessions: (project?: string | null, limit?: number | null) => {
    const qs = new URLSearchParams();
    if (project) qs.set('project', project);
    if (limit) qs.set('limit', String(limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return apiFetch<SessionsResult>(`/admin/system/memory/sessions${suffix}`);
  },

  listTesseraeProjects: () =>
    apiFetch<{ projects: TesseraeProjectState[] }>(
      '/admin/system/memory/tesserae/projects',
    ),

  // enabled=true auto-resolves the workspace from the project (no path needed);
  // enabled=false disables. An explicit `root` overrides the auto-resolution.
  setTesseraeRoot: (projectId: string, enabled: boolean, root: string | null = null) =>
    apiFetch<{ project: TesseraeProjectState }>(
      `/admin/system/memory/tesserae/projects/${encodeURIComponent(projectId)}`,
      {
        method: 'POST',
        body: JSON.stringify({ enabled, root }),
      },
    ),

  setTesseraeDistill: (projectId: string, enabled: boolean) =>
    apiFetch<{ project: TesseraeProjectState }>(
      `/admin/system/memory/tesserae/projects/${encodeURIComponent(projectId)}/distill`,
      {
        method: 'POST',
        body: JSON.stringify({ enabled }),
      },
    ),

  refreshTesserae: (projectId: string) =>
    apiFetch<TesseraeRefreshResult>(
      `/admin/system/memory/tesserae/projects/${encodeURIComponent(projectId)}/refresh`,
      { method: 'POST' },
    ),

  // Per-op buttons surfaced in Settings → Memory System.
  // init + ingest are synchronous (fast). compile + build-site are
  // dispatched to a daemon thread; caller polls via `jobStatus`.
  tesseraeStatus: (projectId: string) =>
    apiFetch<TesseraeWorkspaceStatus>(
      `/admin/system/memory/tesserae/projects/${encodeURIComponent(projectId)}/status`,
    ),

  tesseraeInit: (projectId: string) =>
    apiFetch<TesseraeOpResult>(
      `/admin/system/memory/tesserae/projects/${encodeURIComponent(projectId)}/init`,
      { method: 'POST' },
    ),

  tesseraeIngest: (projectId: string, paths?: string[]) =>
    apiFetch<TesseraeOpResult>(
      `/admin/system/memory/tesserae/projects/${encodeURIComponent(projectId)}/ingest`,
      {
        method: 'POST',
        body: JSON.stringify({ paths: paths || null }),
      },
    ),

  tesseraeCompile: (projectId: string) =>
    apiFetch<TesseraeAsyncJob>(
      `/admin/system/memory/tesserae/projects/${encodeURIComponent(projectId)}/compile`,
      { method: 'POST' },
    ),

  tesseraeBuildSite: (projectId: string) =>
    apiFetch<TesseraeAsyncJob>(
      `/admin/system/memory/tesserae/projects/${encodeURIComponent(projectId)}/build-site`,
      { method: 'POST' },
    ),

  tesseraeJobStatus: (jobId: string) =>
    apiFetch<TesseraeAsyncJob>(
      `/admin/system/memory/tesserae/jobs/${encodeURIComponent(jobId)}`,
    ),

  // --- Background memory/observability queries ---

  // Dispatch a memory/observability query as a background job; poll getMemoryJob.
  runMemoryQuery: (kind: MemoryQueryKind, params?: Record<string, unknown> | null) =>
    apiFetch<{ job_id: string; kind: string; status: 'running' }>(
      '/admin/system/memory/query',
      { method: 'POST', body: JSON.stringify({ kind, params: params ?? null }) },
    ),

  // List past query jobs (newest first, NO result blob). Optional kind filter.
  listMemoryJobs: (kind?: MemoryQueryKind | null, limit?: number | null) => {
    const qs = new URLSearchParams();
    if (kind) qs.set('kind', kind);
    if (limit) qs.set('limit', String(limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return apiFetch<{ jobs: MemoryJobSummary[] }>(`/admin/system/memory/jobs${suffix}`);
  },

  // Read one job WITH its result (shares the tesserae jobs store).
  getMemoryJob: (jobId: string) =>
    apiFetch<MemoryJob>(
      `/admin/system/memory/tesserae/jobs/${encodeURIComponent(jobId)}`,
    ),
};
