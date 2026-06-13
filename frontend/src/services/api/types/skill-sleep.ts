/**
 * Skill-Sleep types — SkillOpt-style skill optimization runs.
 *
 * A run gates a candidate `SKILL.md` against the current one (blind judge,
 * strict improvement) and measures it on a disjoint split. Accepted candidates
 * are STAGED — `adopted_at` stays null until an operator adopts (the only
 * action that writes the candidate to disk).
 */

export type SkillSleepStatus =
  | 'accepted'
  | 'rejected'
  | 'abstained'
  | 'failed'
  | 'no_candidate';

/** Verdict returned by the `sleep` / `sleep/round` endpoints. */
export interface SkillSleepVerdict {
  run_id: number | null;
  status: SkillSleepStatus;
  accepted: boolean;
  current_score: number | null;
  candidate_score: number | null;
  delta: number | null;
  question_count: number;
  reason: string | null;
  /** Disjoint-split outcome block when measured; shape is backend-owned. */
  outcome?: unknown;
}

/** A persisted `skill_sleep_runs` row (the GET response shape). */
export interface SkillSleepRun {
  id: number;
  project_id: string;
  skill_name: string;
  skill_id: string | null;
  status: SkillSleepStatus;
  current_score: number | null;
  candidate_score: number | null;
  delta: number | null;
  question_count: number;
  partition_seed: number | null;
  judge_backend: string | null;
  candidate_body: string | null;
  /** The current SKILL.md body the candidate was gated against (for the diff);
   *  null on pre-migration-164 runs → drawer falls back to candidate-only. */
  current_body: string | null;
  current_body_hash: string | null;
  reason: string | null;
  created_at: string;
  finished_at: string | null;
  /** The adopt gate hinges on this being null (un-adopted). */
  adopted_at: string | null;
  outcome_before_score: number | null;
  outcome_after_score: number | null;
  outcome_delta: number | null;
  outcome_question_count: number | null;
}

export interface SkillSleepRunsResponse {
  runs: SkillSleepRun[];
}

export interface SkillSleepAdoptResponse {
  adopted: boolean;
  run_id: number;
  reason?: string;
}
