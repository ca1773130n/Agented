/**
 * Life-Harness T3 evolution API (typed client).
 *
 * Surfaces the admin endpoints for ``harness_evolution_rounds``:
 *  - List rounds (cross-bot or per-bot)
 *  - Fetch a single round detail
 *  - Trigger dry-run / live evolution
 *  - Approve / abort an ``awaiting_approval`` round
 *
 * Reference: arXiv 2605.22166 (Life-Harness §5.2 Evolution Dynamics).
 */

import { apiFetch } from './client';

export type EvolutionStatus =
  | 'pending'
  | 'running'
  | 'awaiting_approval'
  | 'applied'
  | 'failed'
  | 'aborted';

export type EvolutionOp = 'create' | 'supersede' | 'disable';

export interface EvolutionPatchEntry {
  op: EvolutionOp;
  layer: 'h2' | 'h3' | 'h4' | 'h5';
  name: string;
  existing_layer_id: string | null;
  payload: Record<string, unknown> | null;
}

export interface EvolutionPatch {
  notes: string;
  entries: EvolutionPatchEntry[];
}

export interface EvolutionRound {
  id: string;
  bot_id: string;
  status: EvolutionStatus;
  started_at: string;
  finished_at: string | null;
  input_window_since: string | null;
  input_window_until: string | null;
  input_execution_count: number;
  input_layers: Record<string, unknown>;
  output_patch: EvolutionPatch | null;
  applied_layer_ids: string[];
  error_message: string | null;
  notes: string | null;
  scratch_dir: string | null;
}

export interface EvolutionRunOptions {
  since?: string;
  until?: string;
  limit?: number;
}

export interface EvolutionRunResult {
  round_id: string;
  status: EvolutionStatus;
  applied_layer_ids: string[];
  error: string | null;
  notes: string | null;
}

export interface EvolutionImpactWindow {
  executions: number;
  success_rate: number | null;
  failure_layers: { h2: number; h3: number; h4: number; general: number };
  mean_incident_count: number | null;
}

export interface EvolutionImpactDelta {
  success_rate: number | null;
  mean_incident_count: number | null;
  failure_layers: { h2: number; h3: number; h4: number; general: number };
}

export type EvolutionImpactResponse =
  | { available: false; reason: string }
  | {
      available: true;
      round_id: string;
      bot_id: string;
      window_size: number;
      before: EvolutionImpactWindow;
      after: EvolutionImpactWindow;
      delta: EvolutionImpactDelta;
    };

export const harnessEvolutionApi = {
  /** Cross-bot listing, newest first. */
  listAll: (opts: { limit?: number; status?: EvolutionStatus } = {}) => {
    const params = new URLSearchParams();
    if (opts.limit !== undefined) params.set('limit', String(opts.limit));
    if (opts.status) params.set('status', opts.status);
    const qs = params.toString();
    return apiFetch<{ rounds: EvolutionRound[] }>(
      `/admin/evolution/rounds${qs ? `?${qs}` : ''}`,
    );
  },

  listForBot: (botId: string, limit = 20) =>
    apiFetch<{ bot_id: string; rounds: EvolutionRound[] }>(
      `/admin/bots/${encodeURIComponent(botId)}/evolution/rounds?limit=${limit}`,
    ),

  getRound: (roundId: string) =>
    apiFetch<EvolutionRound>(
      `/admin/evolution/rounds/${encodeURIComponent(roundId)}`,
    ),

  dryRun: (botId: string, opts: EvolutionRunOptions = {}) =>
    apiFetch<EvolutionRunResult>(
      `/admin/bots/${encodeURIComponent(botId)}/evolution/dry-run`,
      { method: 'POST', body: JSON.stringify(opts) },
    ),

  liveRun: (botId: string, opts: EvolutionRunOptions = {}) =>
    apiFetch<EvolutionRunResult>(
      `/admin/bots/${encodeURIComponent(botId)}/evolution/apply`,
      { method: 'POST', body: JSON.stringify(opts) },
    ),

  approve: (roundId: string) =>
    apiFetch<EvolutionRunResult>(
      `/admin/evolution/rounds/${encodeURIComponent(roundId)}/apply`,
      { method: 'POST' },
    ),

  abort: (roundId: string, reason?: string) =>
    apiFetch<EvolutionRunResult>(
      `/admin/evolution/rounds/${encodeURIComponent(roundId)}/abort`,
      {
        method: 'POST',
        body: JSON.stringify({ reason: reason || null }),
      },
    ),

  getImpact: (roundId: string, window = 20) =>
    apiFetch<EvolutionImpactResponse>(
      `/admin/evolution/rounds/${encodeURIComponent(roundId)}/impact?window=${window}`,
    ),
};

/** Status → CSS-var colour for badges + row tints. */
export const EVOLUTION_STATUS_COLOR_VAR: Record<EvolutionStatus, string> = {
  pending: 'var(--accent-amber, #f59e0b)',
  running: 'var(--accent-amber, #f59e0b)',
  awaiting_approval: 'var(--accent-cyan, #06b6d4)',
  applied: 'var(--accent-green, #10b981)',
  failed: 'var(--accent-red, #ef4444)',
  aborted: 'var(--text-tertiary, #6b7280)',
};

export const EVOLUTION_STATUS_LABEL: Record<EvolutionStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  awaiting_approval: 'Awaiting approval',
  applied: 'Applied',
  failed: 'Failed',
  aborted: 'Aborted',
};
