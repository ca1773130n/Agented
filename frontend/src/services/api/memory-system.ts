/**
 * Memory System API — bundled session-memory integrations wired into
 * Agented (per-project knowledge graphs, semantic stores, etc.).
 *
 * Designed to absorb additional memory systems (MemPalace, Cognee,
 * etc.) in the same envelope shape; today, only Tesserae is exposed.
 */

import { apiFetch } from './client';

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
export interface MemoryConfig {
  ok: boolean;
  provider: string | null;
  effort: string | null;
  liveness_ok: boolean | null;
  source: string | null;
  reason: string | null;
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

  // Tesserae `query` — raw retrieval search over the knowledge graph (NO LLM).
  graphQuery: (q: string, topK = 8, kind?: string | null) => {
    const qs = new URLSearchParams({ q, top_k: String(topK) });
    if (kind) qs.set('kind', kind);
    return apiFetch<GraphQueryResult>(`/admin/system/memory/graph/query?${qs.toString()}`);
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
};
