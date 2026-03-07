/**
 * Replay & Diff types.
 */

export interface ReplayComparison {
  id: string;
  original_execution_id: string;
  replay_execution_id: string;
  notes: string | null;
  created_at: string;
}

export interface DiffLine {
  line_number: number;
  type: 'unchanged' | 'added' | 'removed';
  content: string;
}

export interface OutputDiff {
  original_execution_id: string;
  replay_execution_id: string;
  diff_lines: DiffLine[];
  original_line_count: number;
  replay_line_count: number;
  change_summary: {
    added: number;
    removed: number;
    unchanged: number;
  };
}

export interface DiffContextPreview {
  context: string;
  token_estimate: {
    full_tokens: number;
    diff_tokens: number;
    reduction_percent: number;
  };
}
