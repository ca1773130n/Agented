/**
 * GRD 0.4.5 multi-candidate plan-selection API (sub-project #3).
 *
 * Wraps the deterministic `gd select-candidate` / `gd plan-tournament`
 * subcommands surfaced under `/api/projects/{id}/grd/plan/*`. Generation of
 * the `PLAN-N.md` candidates is LLM-driven (the planning session) and lives
 * elsewhere — this module is selection/scoring only.
 */
import { apiFetch } from './client';

/** One scored candidate from `gd select-candidate` (ExtendedCandidateResult). */
export interface PlanCandidate {
  path: string;
  relPath: string;
  base_score: number;
  total_score: number;
  base_breakdown?: {
    completeness: number;
    goal_alignment: number;
    hypothesis_quality: number;
    conciseness: number;
  };
  extended?: {
    must_haves_coverage: number;
    verification_commands: number;
    estimated_tokens: number;
  };
  hard_fail?: { kind: string; dead_end_slug: string; matched: string } | null;
  advisory_warnings?: { dead_end_slug: string; jaccard: number }[];
  cluster?: { cluster_id: number; is_representative: boolean; merged_into: string | null };
}

/** The `gd select-candidate` SelectionResult payload. */
export interface PlanSelectionResult {
  phase: string;
  phaseDir?: string;
  milestone?: string;
  candidates: PlanCandidate[];
  winner: PlanCandidate | null;
  promoted_to: string | null;
  audit_trail_path?: string;
}

export interface SelectCandidateResponse {
  success: boolean;
  data: PlanSelectionResult | null;
  error: string | null;
  mirrored: string | null;
}

/** The mirrored selection row from `GET .../plan/{phase}/selection`. */
export interface MirroredPlanSelection {
  id: string;
  project_id: string;
  phase: string;
  milestone: string | null;
  winner_rel: string | null;
  promoted_to: string | null;
  candidates: PlanCandidate[] | null;
  audit: PlanSelectionResult | null;
  created_at?: string;
  updated_at?: string;
}

export interface SelectCandidateOptions {
  dry_run?: boolean;
  force?: boolean;
  run_verification_commands?: boolean;
}

export const grdPlanningApi = {
  /** Run `gd select-candidate <phase>`. dry_run = preview (no promote/mirror). */
  selectCandidate: (projectId: string, phase: string | number, opts: SelectCandidateOptions = {}) =>
    apiFetch<SelectCandidateResponse>(
      `/api/projects/${projectId}/grd/plan/${phase}/select`,
      { method: 'POST', body: JSON.stringify(opts) },
    ),

  /** The latest mirrored selection for a phase (404 → null caught by caller). */
  getSelection: (projectId: string, phase: string | number) =>
    apiFetch<MirroredPlanSelection>(
      `/api/projects/${projectId}/grd/plan/${phase}/selection`,
    ),

  /** Ad-hoc `gd plan-tournament` over explicit candidate paths (no promotion). */
  planTournament: (projectId: string, phase: string | number, candidates: string[]) =>
    apiFetch<{ success: boolean; data: PlanSelectionResult | null; error: string | null }>(
      `/api/projects/${projectId}/grd/plan/tournament`,
      { method: 'POST', body: JSON.stringify({ phase, candidates }) },
    ),
};
