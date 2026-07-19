/**
 * Skill-Sleep API — SkillOpt-style skill optimization (project-scoped).
 *
 * Mirrors answer-eval.ts. All endpoints live under
 * `/admin/projects/{project_id}/...`. `adopt` is the only call that writes to
 * disk (the staged candidate → SKILL.md); the backend refuses non-accepted,
 * stale, and foreign-project adopts.
 */
import { apiFetch } from './client';
import type {
  SkillSleepAdoptResponse,
  SkillSleepRunsResponse,
  SkillSleepVerdict,
} from './types';

export const skillSleepApi = {
  /** Gate an operator-supplied candidate body against the current skill. */
  sleepCandidate: (
    projectId: string,
    skillName: string,
    body: { candidate_body: string; n?: number; seed?: number; measure?: boolean },
  ) =>
    apiFetch<SkillSleepVerdict>(
      `/admin/projects/${encodeURIComponent(projectId)}/skills/${encodeURIComponent(skillName)}/sleep`,
      {
        method: 'POST',
        body: JSON.stringify({
          candidate_body: body.candidate_body,
          ...(body.n !== undefined ? { n: body.n } : {}),
          ...(body.seed !== undefined ? { seed: body.seed } : {}),
          ...(body.measure !== undefined ? { measure: body.measure } : {}),
        }),
      },
    ),

  /**
   * Kick off one autonomous round (Reflect → [rank] → gate → measure → stage)
   * in the BACKGROUND. Returns a `job_id` immediately — a round takes minutes
   * (up to a 600s codex Reflect), so it must not block the request. Poll
   * `roundStatus` for the verdict; the operator can leave the page meanwhile.
   */
  runRound: (
    projectId: string,
    skillName: string,
    body: { n?: number; seed?: number; measure?: boolean; edit_budget?: number } = {},
  ) =>
    apiFetch<{ job_id: string }>(
      `/admin/projects/${encodeURIComponent(projectId)}/skills/${encodeURIComponent(skillName)}/sleep/round`,
      {
        method: 'POST',
        body: JSON.stringify({
          ...(body.n !== undefined ? { n: body.n } : {}),
          ...(body.seed !== undefined ? { seed: body.seed } : {}),
          ...(body.measure !== undefined ? { measure: body.measure } : {}),
          ...(body.edit_budget !== undefined ? { edit_budget: body.edit_budget } : {}),
        }),
      },
    ),

  /** Poll a background round: `{status: running|done|error, verdict?, error?}`. */
  roundStatus: (projectId: string, skillName: string, jobId: string) =>
    apiFetch<{ status: 'running' | 'done' | 'error'; verdict?: SkillSleepVerdict; error?: string }>(
      `/admin/projects/${encodeURIComponent(projectId)}/skills/${encodeURIComponent(skillName)}/sleep/round/${encodeURIComponent(jobId)}`,
    ),

  /** List this project's Skill-Sleep runs (most recent first). */
  listRuns: (projectId: string) =>
    apiFetch<SkillSleepRunsResponse>(
      `/admin/projects/${encodeURIComponent(projectId)}/skill-sleep`,
    ),

  /** Adopt an accepted run — writes its staged candidate body to SKILL.md. */
  adopt: (projectId: string, runId: number) =>
    apiFetch<SkillSleepAdoptResponse>(
      `/admin/projects/${encodeURIComponent(projectId)}/skill-sleep/${encodeURIComponent(String(runId))}/adopt`,
      { method: 'POST' },
    ),
};
