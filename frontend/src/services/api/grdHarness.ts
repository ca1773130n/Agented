/**
 * GRD life-harness API module (REQ-16 plumbing).
 *
 * Two route groups, two bases:
 *   - Group A — the 16 GRD CLI-wrapper routes under ``/api/projects/{id}/grd/*``
 *     (public api, X-API-Key): health/think/dead-ends/genome/verify-mechanical/
 *     reflections/verdict-counts/evolve.
 *   - Group B — the harness-evolution routes under ``/admin/*`` (admin-gated):
 *     autonomy get/set, evolution rounds (project + global, detail/impact/
 *     apply/abort/revert), shared-forge list, adopt.
 *
 * AUTH NOTE (20-RESEARCH §2 gotcha / §9.3): ``apiFetch`` injects the same
 * credentials on every call — X-API-Key (sessionStorage), the Bearer/HttpOnly
 * session cookie, and X-CSRF-Token on mutating requests — and the ``/admin``
 * router is gated by that same global ApiKey/bearer middleware. So Group B is
 * distinguished purely by the ``/admin`` base path (NOT the ``/api`` base);
 * routing the call to ``/admin/...`` is what carries it through the admin gate.
 * Group A is deliberately sent to the ``/api/projects/...`` base instead.
 */
import { apiFetch } from './client';

// ─── Group A response shapes (CLI-wrapper passthroughs, loosely typed) ───
export interface GrdHealthResult {
  [key: string]: unknown;
}

export interface DeadEndEntry {
  approach: string;
  reason: string;
  phase?: string | null;
}

export interface GenomeSnapshot {
  [key: string]: unknown;
}

export interface EvolveRun {
  id?: string;
  run_id?: string;
  project_id?: string;
  status?: string;
  [key: string]: unknown;
}

/** A mirrored GRD 0.4.x life-harness round (`gd harness round`).
 *  (Distinct from the Group-B ``HarnessRound`` evolution-round shape below.) */
export interface LifeHarnessRound {
  id?: string;
  project_id?: string;
  round_id: string;
  status: string;
  detail?: string | null;
  evidence_count?: number | null;
  patch_hash?: string | null;
  confidence?: number | null;
  summary?: string | null;
  applied_sha?: string | null;
  eval?: Record<string, unknown> | null;
  patch?: Record<string, unknown> | null;
  created_at?: string;
  [key: string]: unknown;
}

// ─── Group B shapes ───
export interface AutonomyConfigResponse {
  project_id: string;
  policy: Record<string, unknown>;
  configured: boolean;
}

export interface HarnessRound {
  round_id: string;
  status?: string;
  [key: string]: unknown;
}

export interface SharedForgeBinding {
  id?: number;
  [key: string]: unknown;
}

export const grdHarnessApi = {
  // ═══════════════════════════ Group A — /api/projects/{id}/grd/* ═══════════════════════════

  /** 1. GET /grd/health — health panel. */
  getHealth: (projectId: string) =>
    apiFetch<GrdHealthResult>(`/api/projects/${projectId}/grd/health`),

  /** 2. POST /grd/think — think briefing. */
  think: (projectId: string) =>
    apiFetch<Record<string, unknown>>(`/api/projects/${projectId}/grd/think`, {
      method: 'POST',
    }),

  /** 3. POST /grd/dead-ends — append a dead-end ({approach, reason, phase?}). */
  addDeadEnd: (
    projectId: string,
    entry: { approach: string; reason: string; phase?: string | null },
  ) =>
    apiFetch<Record<string, unknown>>(`/api/projects/${projectId}/grd/dead-ends`, {
      method: 'POST',
      body: JSON.stringify(entry),
    }),

  /** 4. POST /grd/dead-ends/promote-from-phase/{phase} — promote a phase's dead-ends. */
  promoteDeadEnds: (projectId: string, phase: string) =>
    apiFetch<Record<string, unknown>>(
      `/api/projects/${projectId}/grd/dead-ends/promote-from-phase/${phase}`,
      { method: 'POST' },
    ),

  /** 5. GET /grd/dead-ends — dead-ends list (DB mirror). */
  listDeadEnds: (projectId: string) =>
    apiFetch<{ dead_ends: DeadEndEntry[] }>(`/api/projects/${projectId}/grd/dead-ends`),

  /** 6. GET /grd/genome — genome JSON. */
  getGenome: (projectId: string) =>
    apiFetch<GenomeSnapshot>(`/api/projects/${projectId}/grd/genome`),

  /** 7. POST /grd/genome/snapshot — take a genome snapshot. */
  snapshotGenome: (projectId: string) =>
    apiFetch<GenomeSnapshot>(`/api/projects/${projectId}/grd/genome/snapshot`, {
      method: 'POST',
    }),

  /** 8. GET /grd/genome/snapshots — snapshot history. */
  listGenomeSnapshots: (projectId: string) =>
    apiFetch<{ snapshots: GenomeSnapshot[] }>(
      `/api/projects/${projectId}/grd/genome/snapshots`,
    ),

  /** 9. GET /grd/genome/latest — current/latest snapshot. */
  latestGenomeSnapshot: (projectId: string) =>
    apiFetch<GenomeSnapshot>(`/api/projects/${projectId}/grd/genome/latest`),

  /** 10. POST /grd/verify/mechanical/{phase} — mechanical verify result. */
  verifyMechanical: (projectId: string, phase: string) =>
    apiFetch<Record<string, unknown>>(
      `/api/projects/${projectId}/grd/verify/mechanical/${phase}`,
      { method: 'POST' },
    ),

  /** 11. GET /grd/phases/{phaseId}/reflections — reflections list. */
  listPhaseReflections: (projectId: string, phaseId: string) =>
    apiFetch<{ reflections: unknown[] }>(
      `/api/projects/${projectId}/grd/phases/${phaseId}/reflections`,
    ),

  /** 12. GET /grd/verdict-counts — verdict tallies. */
  verdictCounts: (projectId: string) =>
    apiFetch<Record<string, unknown>>(`/api/projects/${projectId}/grd/verdict-counts`),

  /** 13. POST /grd/evolve/start — start a gd evolve run ({session_id, evolve_run_id}). */
  startEvolve: (
    projectId: string,
    config?: Record<string, unknown>,
  ) =>
    apiFetch<{ session_id: string; evolve_run_id?: string }>(
      `/api/projects/${projectId}/grd/evolve/start`,
      { method: 'POST', body: JSON.stringify(config ?? {}) },
    ),

  /** 14. GET /grd/evolve/runs — runs list. */
  listEvolveRuns: (projectId: string, status?: string, limit = 20) => {
    const qs = new URLSearchParams();
    if (status) qs.set('status', status);
    qs.set('limit', String(limit));
    return apiFetch<{ runs: EvolveRun[] }>(
      `/api/projects/${projectId}/grd/evolve/runs?${qs.toString()}`,
    );
  },

  /** 15. GET /grd/evolve/runs/{runId} — run detail. */
  getEvolveRun: (projectId: string, runId: string) =>
    apiFetch<EvolveRun>(`/api/projects/${projectId}/grd/evolve/runs/${runId}`),

  /** 16. POST /grd/evolve/runs/{runId}/stop — stop a run. */
  stopEvolveRun: (projectId: string, runId: string) =>
    apiFetch<Record<string, unknown>>(
      `/api/projects/${projectId}/grd/evolve/runs/${runId}/stop`,
      { method: 'POST' },
    ),

  // ─── GRD 0.4.x life-harness rounds (supersede gd evolve) ───

  /** Run a `gd harness round` (background; poll listHarnessRounds for the result). */
  runHarnessRound: (
    projectId: string,
    opts?: { auto?: boolean; dry_run?: boolean; full_eval?: boolean },
  ) =>
    apiFetch<{ status: string }>(
      `/api/projects/${projectId}/grd/harness/round`,
      { method: 'POST', body: JSON.stringify(opts ?? {}) },
    ),

  /** List mirrored harness rounds (newest first). */
  listHarnessRounds: (projectId: string, limit = 50) =>
    apiFetch<{ rounds: LifeHarnessRound[] }>(
      `/api/projects/${projectId}/grd/harness/rounds?limit=${limit}`,
    ),

  /** One harness round (incl. patch/eval). */
  getHarnessRound: (projectId: string, roundId: string) =>
    apiFetch<LifeHarnessRound>(
      `/api/projects/${projectId}/grd/harness/rounds/${roundId}`,
    ),

  /** Revert an applied harness round. */
  revertHarnessRound: (projectId: string, roundId: string) =>
    apiFetch<{ success: boolean; output?: string; error?: string }>(
      `/api/projects/${projectId}/grd/harness/rounds/${roundId}/revert`,
      { method: 'POST' },
    ),

  /** Live `gd harness status`. */
  harnessStatus: (projectId: string) =>
    apiFetch<{ success: boolean; rounds: unknown[]; error?: string | null }>(
      `/api/projects/${projectId}/grd/harness/status`,
    ),

  // ═══════════════════════════ Group B — /admin/* (admin-gated) ═══════════════════════════

  /** GET /admin/projects/{id}/autonomy — autonomy editor (read). */
  getAutonomy: (projectId: string) =>
    apiFetch<AutonomyConfigResponse>(`/admin/projects/${projectId}/autonomy`),

  /** PUT /admin/projects/{id}/autonomy — autonomy editor (write). Body wraps {policy}. */
  setAutonomy: (projectId: string, policy: Record<string, unknown>) =>
    apiFetch<{ project_id: string; policy: Record<string, unknown> }>(
      `/admin/projects/${projectId}/autonomy`,
      { method: 'PUT', body: JSON.stringify({ policy }) },
    ),

  /** GET /admin/projects/{id}/evolution/rounds — project-scoped rounds list. */
  listProjectRounds: (projectId: string, limit = 20) =>
    apiFetch<{ project_id: string; rounds: HarnessRound[] }>(
      `/admin/projects/${projectId}/evolution/rounds?limit=${limit}`,
    ),

  /** GET /admin/evolution/rounds — global rounds browse. */
  listAllRounds: (limit = 50, status?: string) => {
    const qs = new URLSearchParams();
    qs.set('limit', String(limit));
    if (status) qs.set('status', status);
    return apiFetch<{ rounds: HarnessRound[] }>(
      `/admin/evolution/rounds?${qs.toString()}`,
    );
  },

  /** GET /admin/evolution/rounds/{roundId} — round detail. */
  getRoundDetail: (roundId: string) =>
    apiFetch<HarnessRound>(`/admin/evolution/rounds/${roundId}`),

  /** GET /admin/evolution/rounds/{roundId}/impact — round impact. */
  getRoundImpact: (roundId: string, window = 20) =>
    apiFetch<Record<string, unknown>>(
      `/admin/evolution/rounds/${roundId}/impact?window=${window}`,
    ),

  /** POST /admin/evolution/rounds/{roundId}/apply — approve a dry-run round. */
  approveRound: (roundId: string) =>
    apiFetch<Record<string, unknown>>(
      `/admin/evolution/rounds/${roundId}/apply`,
      { method: 'POST' },
    ),

  /** POST /admin/evolution/rounds/{roundId}/abort — abort a dry-run round. */
  abortRound: (roundId: string, reason?: string) =>
    apiFetch<Record<string, unknown>>(
      `/admin/evolution/rounds/${roundId}/abort`,
      { method: 'POST', body: JSON.stringify(reason ? { reason } : {}) },
    ),

  /** POST /admin/evolution/rounds/{roundId}/revert — revert an applied round (destructive). */
  revertRound: (roundId: string, force = false) =>
    apiFetch<{ round_id: string; [key: string]: unknown }>(
      `/admin/evolution/rounds/${roundId}/revert`,
      { method: 'POST', body: JSON.stringify(force ? { force } : {}) },
    ),

  /** GET /admin/shared-forge — shared-forge browse. */
  listSharedForge: () =>
    apiFetch<{ shared: SharedForgeBinding[] }>(`/admin/shared-forge`),

  /** POST /admin/projects/{id}/adopt-shared/{bindingId} — adopt a shared binding. */
  adoptShared: (projectId: string, bindingId: number) =>
    apiFetch<{ project_id: string; [key: string]: unknown }>(
      `/admin/projects/${projectId}/adopt-shared/${bindingId}`,
      { method: 'POST' },
    ),
};
