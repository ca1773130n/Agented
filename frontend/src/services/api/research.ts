/**
 * GRD autoresearch API module (REQ-15 plumbing).
 *
 * Wraps the five ``/api/projects/{id}/research/*`` routes shipped in 20-01
 * (the ``gd research`` autoresearch loop) plus the generic session SSE the
 * research session streams over. Pure, typed plumbing — no UI.
 *
 * Streaming note: a research session is a normal PSM session, so its live
 * output is the generic ``/api/projects/{id}/sessions/{sid}/stream`` SSE —
 * exactly the URL ``grdApi.streamSession`` uses (20-01 SUMMARY: "research
 * routes reuse the generic /sessions/{id}/output SSE — no research bridge").
 */
import { apiFetch, createAuthenticatedEventSource } from './client';
import type { AuthenticatedEventSource, AuthenticatedEventSourceOptions } from './client';

/** THREAD.md frontmatter — the row the thread browser / portfolio renders. */
export interface ResearchThread {
  id: string;
  question: string;
  status: string;
  iteration: number;
  max_iterations: number;
}

/** Full thread bundle from GET /research/threads/{id} — each body is None-safe. */
export interface ResearchThreadBundle {
  id: string;
  /** Raw THREAD.md contents (frontmatter + body), or null when absent. */
  thread: string | null;
  /** Raw HYPOTHESES.md contents (the hypothesis ledger), or null when absent. */
  hypotheses: string | null;
  /** Raw FINDING.md contents (the report), or null when absent. */
  finding: string | null;
}

export interface StartResearchResponse {
  session_id: string;
}

/** One selectable option on a checkpoint question (GRD 0.5.0 interactive gates). */
export interface CheckpointOption {
  label: string;
  description?: string;
  /** The option the loop recommends — pre-selected in the UI. */
  recommended?: boolean;
}

/** A single human-decision question raised at a research checkpoint. */
export interface CheckpointQuestion {
  id: string;
  ask: string;
  /** When true the answer needs free-text (the ``text`` field), not just a label. */
  freeform?: boolean;
  options: CheckpointOption[];
}

/**
 * The pending human-decision gate a PAUSED thread is waiting on (GRD 0.5.0).
 * Absent/null when the thread is not paused at a checkpoint.
 */
export interface PendingCheckpoint {
  point: 'seed' | 'hypothesize' | 'design' | 'decide';
  type?: string;
  round?: number;
  context?: string;
  questions: CheckpointQuestion[];
}

/** One resolved answer sent back to ``resume`` to clear a checkpoint question. */
export interface CheckpointAnswer {
  question_id: string;
  /** The chosen option's ``label``. */
  label: string;
  /** Optional free-text — required when the question is ``freeform``. */
  text?: string;
}

/**
 * ``gd research status`` JSON for a thread. Loosely typed (the CLI owns the
 * full shape); the field the checkpoint UI keys off is ``pendingCheckpoint``,
 * present only when the thread is paused awaiting a human decision.
 */
export interface ResearchStatus {
  id?: string;
  status?: string;
  question?: string;
  iteration?: number;
  max_iterations?: number;
  /** The awaiting-decision gate, or null/absent when not paused. */
  pendingCheckpoint?: PendingCheckpoint | null;
  [key: string]: unknown;
}

export interface ResearchThreadsResponse {
  threads: ResearchThread[];
}

/** Optional knobs for a research run (mapped to ``--max-iterations`` / ``--no-gates``). */
export interface StartResearchOptions {
  max_iterations?: number;
  no_gates?: boolean;
  /** GRD 0.4.14 deep-research mode (fresh-run only) — /grd:deep-research. */
  deep?: boolean;
  /** Deep-run only: escalate every subagent to Opus/max (costlier). */
  ultracode?: boolean;
  /**
   * GRD 0.5.0 checkpoint steering posture (fresh-run only). One of three:
   * ``autopilot`` (default) — headless, GRD resolves each checkpoint to its
   * recommended default; ``panel`` — headless, GRD's multi-backend AI panel
   * decides each SEED/HYPOTHESIZE/DESIGN/DECIDE gate (degrade-safe); ``attended``
   * — the loop PAUSES at each gate for a human (surfaced via CheckpointPanel).
   */
  research_steering?: 'autopilot' | 'panel' | 'attended';
  /**
   * Resume-only: answers that resolve a pending checkpoint (GRD 0.5.0). One
   * entry per checkpoint question; forwarded as ``--answers`` to ``gd research
   * resume``. Ignored by ``startResearch``.
   */
  answers?: CheckpointAnswer[];
}

/** One /grd:deep-research report on disk (GET /research/deep-reports). */
export interface DeepReportSummary {
  name: string;
  milestone: string;
  path: string;
  modified: number;
}

/** A single deep-research report's markdown (GET /research/deep-reports/{name}). */
export interface DeepReport {
  name: string;
  markdown: string | null;
}

/** GET /research/deep-reports response envelope. */
export interface DeepReportsResponse {
  reports: DeepReportSummary[];
}

/** Merge optional run knobs onto a request body (only the ones provided). */
function withResearchOpts(
  body: Record<string, unknown>,
  opts?: StartResearchOptions,
): Record<string, unknown> {
  if (opts?.max_iterations !== undefined) body.max_iterations = opts.max_iterations;
  if (opts?.no_gates !== undefined) body.no_gates = opts.no_gates;
  return body;
}

export const researchApi = {
  /**
   * POST /api/projects/{id}/research/start — spawn a ``grd_research`` session
   * for ``question``. Returns the session id to stream/observe.
   */
  startResearch: (
    projectId: string,
    question: string,
    opts?: StartResearchOptions,
  ) => {
    const body = withResearchOpts({ question }, opts);
    if (opts?.deep) body.deep = true;
    if (opts?.ultracode) body.ultracode = true;
    if (opts?.research_steering) body.research_steering = opts.research_steering;
    return apiFetch<StartResearchResponse>(
      `/api/projects/${projectId}/research/start`,
      { method: 'POST', body: JSON.stringify(body) },
    );
  },

  /**
   * POST /api/projects/{id}/research/{threadId}/resume — resume an existing
   * thread (no question required; the thread carries its own). Optional knobs
   * mirror startResearch.
   */
  resumeThread: (
    projectId: string,
    threadId: string,
    opts?: StartResearchOptions,
  ) => {
    const body = withResearchOpts({}, opts);
    if (opts?.answers !== undefined) body.answers = opts.answers;
    return apiFetch<StartResearchResponse>(
      `/api/projects/${projectId}/research/${threadId}/resume`,
      { method: 'POST', body: JSON.stringify(body) },
    );
  },

  /**
   * GET /api/projects/{id}/research/status?thread_id={id} — the ``gd research
   * status`` JSON for one thread. A PAUSED thread carries ``pendingCheckpoint``
   * (the human-decision gate to resolve); it is null/absent otherwise.
   */
  getStatus: (projectId: string, threadId: string) =>
    apiFetch<ResearchStatus>(
      `/api/projects/${projectId}/research/status?thread_id=${encodeURIComponent(threadId)}`,
    ),

  /** GET /api/projects/{id}/research/threads — the thread browser / portfolio. */
  listThreads: (projectId: string) =>
    apiFetch<ResearchThreadsResponse>(`/api/projects/${projectId}/research/threads`),

  /** GET /api/projects/{id}/research/threads/{threadId} — THREAD/HYPOTHESES/FINDING bundle. */
  getThread: (projectId: string, threadId: string) =>
    apiFetch<ResearchThreadBundle>(
      `/api/projects/${projectId}/research/threads/${threadId}`,
    ),

  /** GET /api/projects/{id}/research/deep-reports — the deep-research report list. */
  listDeepReports: (projectId: string) =>
    apiFetch<DeepReportsResponse>(`/api/projects/${projectId}/research/deep-reports`),

  /** GET /api/projects/{id}/research/deep-reports/{name} — one report's markdown. */
  getDeepReport: (projectId: string, name: string) =>
    apiFetch<DeepReport>(
      `/api/projects/${projectId}/research/deep-reports/${encodeURIComponent(name)}`,
    ),

  /**
   * SSE stream for a running research session — returns an EventSource
   * directly (NOT a Promise), mirroring ``grdApi.streamSession``. Research
   * reuses the generic session-stream URL; caller attaches handlers + close().
   */
  streamResearch: (
    projectId: string,
    sessionId: string,
    options?: AuthenticatedEventSourceOptions,
  ): AuthenticatedEventSource =>
    createAuthenticatedEventSource(
      `/api/projects/${projectId}/sessions/${sessionId}/stream`,
      options,
    ),
};
