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

export interface ResearchThreadsResponse {
  threads: ResearchThread[];
}

/** Optional knobs for a research run (mapped to ``--max-iterations`` / ``--no-gates``). */
export interface StartResearchOptions {
  max_iterations?: number;
  no_gates?: boolean;
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
    const body: Record<string, unknown> = { question };
    if (opts?.max_iterations !== undefined) body.max_iterations = opts.max_iterations;
    if (opts?.no_gates !== undefined) body.no_gates = opts.no_gates;
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
    const body: Record<string, unknown> = {};
    if (opts?.max_iterations !== undefined) body.max_iterations = opts.max_iterations;
    if (opts?.no_gates !== undefined) body.no_gates = opts.no_gates;
    return apiFetch<StartResearchResponse>(
      `/api/projects/${projectId}/research/${threadId}/resume`,
      { method: 'POST', body: JSON.stringify(body) },
    );
  },

  /** GET /api/projects/{id}/research/threads — the thread browser / portfolio. */
  listThreads: (projectId: string) =>
    apiFetch<ResearchThreadsResponse>(`/api/projects/${projectId}/research/threads`),

  /** GET /api/projects/{id}/research/threads/{threadId} — THREAD/HYPOTHESES/FINDING bundle. */
  getThread: (projectId: string, threadId: string) =>
    apiFetch<ResearchThreadBundle>(
      `/api/projects/${projectId}/research/threads/${threadId}`,
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
