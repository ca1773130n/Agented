/**
 * Replay and diff-context API module.
 *
 * Provides functions for triggering execution replays, fetching comparisons,
 * viewing side-by-side diffs, and previewing diff-aware context extraction.
 */
import { apiFetch } from './client';
import type { ReplayComparison, OutputDiff, DiffContextPreview } from './types';

export const replayApi = {
  // Replay an execution
  create: (executionId: string, notes?: string) =>
    apiFetch<{ comparison_id: string; original_execution_id: string; replay_execution_id: string }>(
      `/admin/executions/${executionId}/replay`,
      { method: 'POST', body: JSON.stringify({ notes }) }
    ),

  // List comparisons for an execution
  getComparisons: (executionId: string) =>
    apiFetch<{ comparisons: ReplayComparison[] }>(
      `/admin/executions/${executionId}/comparisons`
    ),

  // Get a specific comparison
  getComparison: (comparisonId: string) =>
    apiFetch<ReplayComparison>(`/admin/replay-comparisons/${comparisonId}`),

  // Get side-by-side diff for a comparison
  getDiff: (comparisonId: string) =>
    apiFetch<OutputDiff>(`/admin/replay-comparisons/${comparisonId}/diff`),

  // Preview diff-aware context extraction
  previewDiffContext: (diffText: string, contextLines?: number) =>
    apiFetch<DiffContextPreview>(
      `/admin/diff-context/preview`,
      { method: 'POST', body: JSON.stringify({ diff_text: diffText, context_lines: contextLines }) }
    ),
};
