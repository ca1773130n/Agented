/**
 * Competitor-intelligence API module (phase 23, REQ-27 add / REQ-30 ranked signals).
 *
 * Mirrors the per-domain module convention (budgets.ts / grd.ts): shared
 * `apiFetch` for the JSON routes, and `createAuthenticatedEventSource` for the
 * SSE signals stream (the same authenticated-SSE helper every other live view
 * uses). Project-scoped: every call takes a `projectId`.
 */
import { apiFetch, createAuthenticatedEventSource } from './client';
import type { AuthenticatedEventSource, AuthenticatedEventSourceOptions } from './client';

/** A watched competitor source (migration-171 `competitor_source` row). */
export interface CompetitorSource {
  id: string;
  project_id: string;
  /** Auto-detected from the URL host. */
  kind: 'github_repo' | 'arxiv' | 'product_url' | string;
  url: string;
  origin: string;
  etag: string | null;
  watermark: string | null;
  status: string;
  /** Optional operator display name (never required to add). */
  label: string | null;
  created_at: string;
}

/**
 * A ranked, AI-summarized change (migration-171 `detected_signal` row joined
 * to its source). The dashboard renders these ordered by `score` desc.
 */
export interface DetectedSignal {
  id: string;
  source_id: string;
  summary: string | null;
  signal_type: string | null;
  /** Relevance score in [0,1]; ranking key. May be null for an unscored row. */
  score: number | null;
  created_at: string;
  /** Joined from competitor_source so a signal can be labeled inline. */
  kind: string | null;
  url: string | null;
  label: string | null;
}

export const competitorIntelApi = {
  /**
   * Add a source by URL. `label` is optional — omit it freely; the backend
   * auto-detects `kind` and never rejects a missing/blank label (REQ-27).
   */
  addSource: (
    projectId: string,
    url: string,
    label?: string,
  ): Promise<{ source: CompetitorSource }> =>
    apiFetch<{ source: CompetitorSource }>(
      `/api/projects/${projectId}/competitor-intel/sources`,
      {
        method: 'POST',
        body: JSON.stringify({ url, label }),
      },
    ),

  /** List the project's watched sources, newest first. */
  listSources: (projectId: string): Promise<{ sources: CompetitorSource[] }> =>
    apiFetch<{ sources: CompetitorSource[] }>(
      `/api/projects/${projectId}/competitor-intel/sources`,
    ),

  /** Ranked detected signals for the project (score desc, created_at desc). */
  listSignals: (projectId: string): Promise<{ signals: DetectedSignal[] }> =>
    apiFetch<{ signals: DetectedSignal[] }>(
      `/api/projects/${projectId}/competitor-intel/signals`,
    ),

  /** Relative URL of the signals SSE stream (for diagnostics / native consumers). */
  signalsStreamUrl: (projectId: string): string =>
    `/api/projects/${projectId}/competitor-intel/signals/stream`,

  /**
   * Open an authenticated SSE stream of newly-ranked signals. Returns an
   * `AuthenticatedEventSource` directly (NOT a Promise) — the caller subscribes
   * to the `signal` / `done` events and owns the lifecycle (`.close()`), exactly
   * like `grdApi.streamHarnessSetup`.
   */
  streamSignals: (
    projectId: string,
    options?: AuthenticatedEventSourceOptions,
  ): AuthenticatedEventSource =>
    createAuthenticatedEventSource(
      `/api/projects/${projectId}/competitor-intel/signals/stream`,
      options,
    ),
};
