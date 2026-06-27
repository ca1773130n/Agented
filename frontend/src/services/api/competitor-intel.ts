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
  /** Last time the poller fetched this source (UTC); null until first polled. */
  last_polled_at: string | null;
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

/**
 * A competitor strategy (phase-26 `competitor_strategy` row, migration 174): a
 * behavior-only proposal synthesized from selected `detected_signal`s, awaiting
 * the operator's review → approve/reject/edit and the §5B legal checklist. The
 * `legal_checklist` records each of the 7 canonical items; `legal_cleared_at` is
 * non-null ONLY when all 7 are affirmed (the non-bypassable implement gate — the
 * UI keeps the implement affordance disabled until it is set).
 */
export interface Strategy {
  id: string;
  project_id: string;
  /** The `detected_signal` ids this strategy synthesizes. */
  signal_ids: string[] | null;
  title: string | null;
  body: string | null;
  /** LLM provenance (multi-backend). */
  backend_kind: string | null;
  model: string | null;
  status: 'proposed' | 'approved' | 'rejected' | 'implementing' | 'done';
  /** Map of the 7 canonical §5B item keys → affirmed bool; null until first affirmed. */
  legal_checklist: Record<string, boolean> | null;
  /** Non-null ONLY when all 7 legal items are affirmed — the visible implement gate. */
  legal_cleared_at: string | null;
  /** Stamped by the 26-04 materialize path; null in this MVP. */
  plan_id: string | null;
  /** The auto-implement goal-loop session (26-05); non-null once an agent run has
   *  been launched for this materialized strategy. */
  session_id?: string | null;
  created_at: string;
  /** True when the strategy was synthesized in degraded mode (LLM backend
   *  unreachable → placeholder body). Present only on the generate response. */
  degraded?: boolean;
}

/**
 * A market-lookalike suggestion (phase-27 `discovery_suggestion` row,
 * `kind='company'`): a competitor company/product a provider-pluggable lookalike
 * scan found *similar* to the project, awaiting an operator verdict. Reuses the
 * P2 `discovery_suggestion` surface (zero migrations) — same shape as
 * `SuggestedCompetitor`, but the candidate is a company/product domain rather
 * than a github repo. The operator can `accept` it (→ a watched `product_url`
 * `competitor_source`) or `dismiss` it.
 */
export interface MarketLookalike {
  id: string;
  project_id: string;
  /** Suggestion kind — `'company'` (a scan writes this) or `'product'`. */
  kind: string;
  /** The resolving provider's name (stored in the `candidate_owner` column). */
  candidate_owner: string;
  /** The candidate's normalized domain (stored in the `candidate_repo` column). */
  candidate_repo: string;
  /** Canonical candidate URL (rendered as the lookalike's link). */
  candidate_url: string;
  /** Deterministic human "why" string, rendered from `evidence.reason`. */
  reason: string | null;
  /** Relevance score; ranking key. May be null (a null score never blocks). */
  score: number | null;
  /** Parsed `evidence` blob (the provider's "why" payload). */
  evidence: Record<string, unknown> | unknown[] | string | null;
  status: 'suggested' | 'added' | 'dismissed';
  /** Stamped with the promoted `competitor_source` id once accepted. */
  source_id: string | null;
  created_at: string;
}

/**
 * The GLOBAL scheduled-poll config (NOT per-project). One APScheduler job polls
 * every active competitor source across all projects, so this enable/interval
 * toggle is a single instance-wide setting.
 */
export interface CompetitorIntelConfig {
  enabled: boolean;
  polling_minutes: number;
}

export const competitorIntelApi = {
  /** Read the GLOBAL scheduled-poll config ({enabled, polling_minutes}). */
  getConfig: (): Promise<CompetitorIntelConfig> =>
    apiFetch<CompetitorIntelConfig>(`/api/competitor-intel/config`),

  /**
   * Enable/disable the GLOBAL scheduled poll + set its interval (runtime, no
   * restart). `polling_minutes` must be one of 5/15/30/60. CSRF auto-injected.
   */
  saveConfig: (config: CompetitorIntelConfig): Promise<CompetitorIntelConfig> =>
    apiFetch<CompetitorIntelConfig>(`/api/competitor-intel/config`, {
      method: 'POST',
      body: JSON.stringify(config),
    }),

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

  /**
   * Delete a watched source. The backend CASCADES — the source's snapshots and
   * detected signals go with it — and is IDOR-safe (404 if the source isn't this
   * project's). Returns the deleted id. CSRF is auto-injected by the client.
   */
  deleteSource: (projectId: string, sourceId: string): Promise<{ deleted: string }> =>
    apiFetch<{ deleted: string }>(
      `/api/projects/${projectId}/competitor-intel/sources/${sourceId}`,
      { method: 'DELETE' },
    ),

  /**
   * Operator-triggered "check now": force-poll this project's active sources
   * immediately (bypassing the per-kind interval floor). Returns whether the
   * poll ran and how many sources produced a new snapshot this run. CSRF is
   * auto-injected by the client for POST.
   */
  pollNow: (projectId: string): Promise<{ polled: boolean; changed: number }> =>
    apiFetch<{ polled: boolean; changed: number }>(
      `/api/projects/${projectId}/competitor-intel/poll`,
      { method: 'POST' },
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

  /**
   * Generate a behavior-only strategy proposal from the selected signal ids
   * (phase-26 P4). The backend runs the multi-backend, taint-wrapped LLM call
   * off the event loop and persists a `'proposed'` strategy. `backendKind` /
   * `modelOverride` are optional (multi-backend, never claude-only); CSRF is
   * auto-injected for POST.
   */
  generateStrategy: (
    projectId: string,
    signalIds: string[],
    opts?: { backendKind?: string; modelOverride?: string },
  ): Promise<{ strategy: Strategy }> =>
    apiFetch<{ strategy: Strategy }>(
      `/api/projects/${projectId}/strategies/generate`,
      {
        method: 'POST',
        body: JSON.stringify({
          signal_ids: signalIds,
          backend_kind: opts?.backendKind,
          model_override: opts?.modelOverride,
        }),
      },
    ),

  /** List the project's strategies, newest first. */
  listStrategies: (projectId: string): Promise<{ strategies: Strategy[] }> =>
    apiFetch<{ strategies: Strategy[] }>(
      `/api/projects/${projectId}/strategies`,
    ),

  /** Approve a strategy (`proposed` → `approved`). */
  approveStrategy: (projectId: string, id: string): Promise<{ strategy: Strategy }> =>
    apiFetch<{ strategy: Strategy }>(
      `/api/projects/${projectId}/strategies/${id}/approve`,
      { method: 'POST' },
    ),

  /** Reject a strategy (→ `rejected`). */
  rejectStrategy: (projectId: string, id: string): Promise<{ strategy: Strategy }> =>
    apiFetch<{ strategy: Strategy }>(
      `/api/projects/${projectId}/strategies/${id}/reject`,
      { method: 'POST' },
    ),

  /** Implement step: materialize an approved + §5B-cleared strategy into a ProjectPlan. */
  materializeStrategy: (projectId: string, id: string): Promise<{ strategy: Strategy; plan: unknown }> =>
    apiFetch<{ strategy: Strategy; plan: unknown }>(
      `/api/projects/${projectId}/strategies/${id}/materialize`,
      { method: 'POST' },
    ),

  /**
   * Launch the TRIPLE-GATED auto-implement goal-loop for a MATERIALIZED strategy:
   * spawns an autonomous coding agent in an ISOLATED git worktree behind a human
   * gate. Requires the AGENTED_STRATEGY_AUTOIMPLEMENT env flag (else 403), §5B
   * legal clearance (else 409), a materialized plan_id (else 409), and a non-empty
   * confirm_token (else 400). Returns the spawned session on success.
   */
  autoimplementStrategy: (
    projectId: string,
    id: string,
    confirmToken: string,
  ): Promise<{ status: string; session_id: string; plan_id: string; worktree_path: string }> =>
    apiFetch(`/api/projects/${projectId}/strategies/${id}/autoimplement`, {
      method: 'POST',
      body: JSON.stringify({ confirm_token: confirmToken }),
    }),

  /**
   * Edit a strategy's title/body. RESETS the §5B legal clearance (the backend
   * flips `independent_authorship` + `no_copied_code` back to false and NULLs
   * `legal_cleared_at`), forcing re-affirmation.
   */
  editStrategy: (
    projectId: string,
    id: string,
    patch: { title?: string; body?: string },
  ): Promise<{ strategy: Strategy }> =>
    apiFetch<{ strategy: Strategy }>(
      `/api/projects/${projectId}/strategies/${id}/edit`,
      { method: 'POST', body: JSON.stringify(patch) },
    ),

  /**
   * Affirm/deny ONE §5B legal-checklist item. Returns the updated strategy so
   * the caller can observe `legal_cleared_at` flip when all 7 are affirmed.
   */
  recordLegalItem: (
    projectId: string,
    id: string,
    itemKey: string,
    value: boolean,
  ): Promise<{ strategy: Strategy }> =>
    apiFetch<{ strategy: Strategy }>(
      `/api/projects/${projectId}/strategies/${id}/legal`,
      { method: 'POST', body: JSON.stringify({ item_key: itemKey, value }) },
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

/**
 * Market-lookalike API (phase-27 P5): a provider-pluggable scan→review→accept
 * loop over the P2 `discovery_suggestion` surface (`kind='company'`). Every call
 * is project-scoped and IDOR-guarded server-side. The `scan` route is BUY-gated:
 * with NO provider keyed it returns a NORMAL 200 with `{provider: null,
 * outcome: 'not_configured', ...}` — the UI renders the "configure a provider"
 * CTA (no crash, no fake data). CSRF is auto-injected by the client for POST.
 */
export const lookalikeApi = {
  /**
   * Run a provider-aware market-lookalike scan. With no provider keyed this
   * resolves to `{provider: null, outcome: 'not_configured', scanned: 0,
   * suggestions: []}` (a 200, NOT an error). `seed` is the operator's seed term.
   */
  scan: (
    projectId: string,
    seed?: string,
  ): Promise<{
    provider: string | null;
    outcome: string;
    scanned: number;
    suggestions: MarketLookalike[];
  }> =>
    apiFetch<{
      provider: string | null;
      outcome: string;
      scanned: number;
      suggestions: MarketLookalike[];
    }>(`/api/projects/${projectId}/lookalikes/scan`, {
      method: 'POST',
      body: JSON.stringify({ seed }),
    }),

  /**
   * The market-lookalike review queue. `provider` is the active provider name
   * (or `null` — the CTA-vs-queue signal); `suggestions` are the market-kind
   * (`company`/`product`) `suggested` rows only.
   */
  listSuggestions: (
    projectId: string,
  ): Promise<{ provider: string | null; suggestions: MarketLookalike[] }> =>
    apiFetch<{ provider: string | null; suggestions: MarketLookalike[] }>(
      `/api/projects/${projectId}/lookalikes/suggestions`,
    ),

  /**
   * Accept a lookalike → promote it into a watched competitor source on the
   * `product_url` lane (`origin='discovery'`). Returns the newly minted source
   * (+ the updated suggestion).
   */
  accept: (
    projectId: string,
    id: string,
  ): Promise<{ source: CompetitorSource; suggestion: MarketLookalike }> =>
    apiFetch<{ source: CompetitorSource; suggestion: MarketLookalike }>(
      `/api/projects/${projectId}/lookalikes/suggestions/${id}/accept`,
      { method: 'POST' },
    ),

  /** Dismiss a lookalike (flip its status to `dismissed`; sticky on re-scan). */
  dismiss: (
    projectId: string,
    id: string,
  ): Promise<{ suggestion: MarketLookalike }> =>
    apiFetch<{ suggestion: MarketLookalike }>(
      `/api/projects/${projectId}/lookalikes/suggestions/${id}/dismiss`,
      { method: 'POST' },
    ),
};
