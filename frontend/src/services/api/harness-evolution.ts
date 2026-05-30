/**
 * Life-Harness evolution API (project-scoped, Forge-aware).
 *
 * Codex-driven rounds operate on a project's Forge bindings (rules /
 * hooks / commands / mcp_servers). Skills are read-only here — the
 * evolver can propose them in NOTES but can't auto-apply.
 *
 * Reference: arXiv 2605.22166 §5.2.
 */

import { apiFetch } from './client';

export type EvolutionStatus =
  | 'pending'
  | 'running'
  | 'awaiting_approval'
  | 'applied'
  | 'failed'
  | 'aborted';

export type EvolutionOp = 'create' | 'update' | 'delete';
export type ForgeKind = 'rule' | 'hook' | 'command' | 'mcp_server' | 'skill';

export interface EvolutionPatchEntry {
  op: EvolutionOp;
  kind: ForgeKind;
  name: string;
  existing_asset_id: number | string | null;
  payload: Record<string, unknown> | null;
}

export interface EvolutionPatch {
  notes: string;
  entries: EvolutionPatchEntry[];
}

export interface AppliedAssetRef {
  kind: ForgeKind;
  op: EvolutionOp;
  asset_id: number | string;
}

export interface EvolutionRound {
  id: string;
  project_id: string;
  status: EvolutionStatus;
  started_at: string;
  finished_at: string | null;
  input_window_since: string | null;
  input_window_until: string | null;
  input_execution_count: number;
  input_forge: Record<string, unknown>;
  output_patch: EvolutionPatch | null;
  applied_asset_ids: AppliedAssetRef[];
  error_message: string | null;
  notes: string | null;
  scratch_dir: string | null;
  auto_applied?: number;
  auto_apply_reason?: Record<string, unknown> | null;
  auto_apply_blocked_reason?: Record<string, unknown> | null;
}

export interface EvolutionRunOptions {
  since?: string;
  until?: string;
  limit?: number;
  force?: boolean;
}

export interface EvolutionRunResult {
  round_id: string;
  status: EvolutionStatus;
  applied_asset_ids: AppliedAssetRef[];
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
      project_id: string;
      window_size: number;
      before: EvolutionImpactWindow;
      after: EvolutionImpactWindow;
      delta: EvolutionImpactDelta;
    };

export const harnessEvolutionApi = {
  listAll: (opts: { limit?: number; status?: EvolutionStatus } = {}) => {
    const params = new URLSearchParams();
    if (opts.limit !== undefined) params.set('limit', String(opts.limit));
    if (opts.status) params.set('status', opts.status);
    const qs = params.toString();
    return apiFetch<{ rounds: EvolutionRound[] }>(
      `/admin/evolution/rounds${qs ? `?${qs}` : ''}`,
    );
  },

  listForProject: (projectId: string, limit = 20) =>
    apiFetch<{ project_id: string; rounds: EvolutionRound[] }>(
      `/admin/projects/${encodeURIComponent(projectId)}/evolution/rounds?limit=${limit}`,
    ),

  getRound: (roundId: string) =>
    apiFetch<EvolutionRound>(
      `/admin/evolution/rounds/${encodeURIComponent(roundId)}`,
    ),

  dryRun: (projectId: string, opts: EvolutionRunOptions = {}) =>
    apiFetch<EvolutionRunResult>(
      `/admin/projects/${encodeURIComponent(projectId)}/evolution/dry-run`,
      { method: 'POST', body: JSON.stringify(opts) },
    ),

  liveRun: (projectId: string, opts: EvolutionRunOptions = {}) =>
    apiFetch<EvolutionRunResult>(
      `/admin/projects/${encodeURIComponent(projectId)}/evolution/apply`,
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

export const FORGE_KIND_COLOR_VAR: Record<ForgeKind, string> = {
  rule: 'var(--accent-cyan, #06b6d4)',
  hook: 'var(--accent-red, #ef4444)',
  command: 'var(--accent-amber, #f59e0b)',
  mcp_server: 'var(--accent-green, #10b981)',
  skill: 'var(--text-tertiary, #6b7280)',
};
