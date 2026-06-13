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

  /** Run one autonomous round: Reflect → [rank] → gate → measure → stage. */
  runRound: (
    projectId: string,
    skillName: string,
    body: { n?: number; seed?: number; measure?: boolean; edit_budget?: number } = {},
  ) =>
    apiFetch<SkillSleepVerdict>(
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
