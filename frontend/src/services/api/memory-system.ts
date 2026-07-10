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
