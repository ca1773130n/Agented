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
  /**
   * Source kind. Auto-detected from the URL host for URL sources; for an
   * `hn_query` source it is supplied EXPLICITLY (the identifier is a search
   * query, not a URL, so there is no host to detect from).
   */
  kind: 'github_repo' | 'arxiv' | 'product_url' | 'job_board' | 'hn_query' | string;
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

/**
 * A ranked discovery suggestion (phase-24 `discovery_suggestion` row): a repo
 * the discovery scan found *similar* to the project's watched github seeds,
 * awaiting an operator verdict. Carries a human-readable `reason` ("why") and a
 * `score`; the operator can `accept` it (→ a watched `competitor_source`,
 * `origin='discovery'`) or `dismiss` it.
 */
export interface SuggestedCompetitor {
  id: string;
  project_id: string;
  /** Candidate kind (defaults to `'github_repo'`). */
  kind: string;
  /** GitHub owner/org of the candidate. */
  candidate_owner: string;
  /** Candidate repo name. */
  candidate_repo: string;
  /** Canonical candidate URL (rendered as the suggestion's link). */
  candidate_url: string;
  /** Deterministic human "why" string, rendered from `evidence`. */
  reason: string | null;
  /** Relevance score; ranking key. May be null (a null score never blocks). */
  score: number | null;
  /** Parsed `evidence` blob (shared_topics, shared_stargazers, …). */
  evidence: Record<string, unknown> | unknown[] | string | null;
  status: 'suggested' | 'added' | 'dismissed';
  /** Stamped with the promoted `competitor_source` id once accepted. */
  source_id: string | null;
  created_at: string;
}

export const competitorIntelApi = {
  /**
   * Add a source by URL (or, for `hn_query`, a search query in the `url` field).
   * `label` is optional — omit it freely; the backend never rejects a
   * missing/blank label (REQ-27). `kind` is optional: omit it for URL sources
   * (the backend auto-detects from the host) and pass `'hn_query'` to register a
   * non-URL search query (a company/product name) the backend can't host-detect.
   */
  addSource: (
    projectId: string,
    url: string,
    label?: string,
    kind?: string,
  ): Promise<{ source: CompetitorSource }> =>
    apiFetch<{ source: CompetitorSource }>(
      `/api/projects/${projectId}/competitor-intel/sources`,
      {
        method: 'POST',
        body: JSON.stringify({ url, label, kind }),
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

  /**
   * Run the discovery scan over the project's watched github seeds (heavy,
   * read-only GitHub fan-out — the backend runs it off the event loop). Returns
   * how many seeds were scanned, how many suggestions were written, and the
   * resolved README lens.
   */
  runDiscovery: (
    projectId: string,
  ): Promise<{ scanned: number; suggestions: number; readme_mode: string }> =>
    apiFetch<{ scanned: number; suggestions: number; readme_mode: string }>(
      `/api/projects/${projectId}/discovery/scan`,
      { method: 'POST' },
    ),

  /** The active discovery review queue (`status='suggested'`, highest score first). */
  listSuggestions: (projectId: string): Promise<{ suggestions: SuggestedCompetitor[] }> =>
    apiFetch<{ suggestions: SuggestedCompetitor[] }>(
      `/api/projects/${projectId}/discovery/suggestions`,
    ),

  /**
   * Accept a suggestion → promote it into a watched competitor source
   * (`origin='discovery'`). Returns the newly minted source (+ the updated
   * suggestion). CSRF is auto-injected by the client for POST.
   */
  acceptSuggestion: (
    projectId: string,
    id: string,
  ): Promise<{ source: CompetitorSource; suggestion: SuggestedCompetitor }> =>
    apiFetch<{ source: CompetitorSource; suggestion: SuggestedCompetitor }>(
      `/api/projects/${projectId}/discovery/suggestions/${id}/accept`,
      { method: 'POST' },
    ),

  /** Dismiss a suggestion (flip its status to `dismissed`; sticky on re-scan). */
  dismissSuggestion: (
    projectId: string,
    id: string,
  ): Promise<{ suggestion: SuggestedCompetitor }> =>
    apiFetch<{ suggestion: SuggestedCompetitor }>(
      `/api/projects/${projectId}/discovery/suggestions/${id}/dismiss`,
      { method: 'POST' },
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
