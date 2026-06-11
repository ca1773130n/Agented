/**
 * Answer-eval API — baseline-vs-pipeline evaluation runs.
 */
import { apiFetch } from './client';

// Types

export interface AnswerEvalRun {
  id: number;
  project_id: string;
  question_count: number;
  judge_backend: string | null;
  baseline_groundedness: number | null;
  baseline_sufficiency: number | null;
  baseline_quality: number | null;
  pipeline_groundedness: number | null;
  pipeline_sufficiency: number | null;
  pipeline_quality: number | null;
  delta_groundedness: number | null;
  delta_sufficiency: number | null;
  delta_quality: number | null;
  status: 'running' | 'complete' | 'failed';
  created_at: string;
  finished_at: string | null;
  /** Project name — joined on the backend when listing globally. */
  project_name?: string | null;
}

export interface AnswerEvalResult {
  id: number;
  run_id: number;
  question: string;
  arm: 'baseline' | 'pipeline';
  answer_text: string | null;
  groundedness: number | null;
  sufficiency: number | null;
  quality: number | null;
  judge_reason: string | null;
  tokens: number | null;
  cost_usd: number | null;
  created_at: string;
}

export interface AnswerEvalRunDetail extends AnswerEvalRun {
  results: AnswerEvalResult[];
}

export interface ListRunsResponse {
  runs: AnswerEvalRun[];
}

export interface StartRunResponse {
  run_id: number;
}

// API object

export const answerEvalApi = {
  /** List eval runs — optionally scoped to a project. */
  listRuns: (projectId?: string) => {
    const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
    return apiFetch<ListRunsResponse>(`/admin/answer-eval/runs${query}`);
  },

  /** Get a single run with its per-question results. */
  getRun: (id: number) => apiFetch<AnswerEvalRunDetail>(`/admin/answer-eval/runs/${id}`),

  /** Start a new eval run (async — returns immediately with run_id). */
  startRun: (projectId: string, n?: number) =>
    apiFetch<StartRunResponse>('/admin/answer-eval/run', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, ...(n !== undefined ? { n } : {}) }),
    }),
};
