/**
 * Minimal line-level diff (LCS) — no dependency. Produces an ordered list of
 * unchanged / removed (in `before`, not `after`) / added (in `after`, not
 * `before`) lines, for rendering a current-vs-candidate skill-body diff.
 */
export type DiffRowType = 'unchanged' | 'added' | 'removed';

export interface DiffRow {
  type: DiffRowType;
  text: string;
}

export interface DiffSummary {
  added: number;
  removed: number;
  unchanged: number;
}

export interface LineDiff {
  rows: DiffRow[];
  summary: DiffSummary;
}

/**
 * Diff two texts by line via a longest-common-subsequence DP. `before` lines
 * absent from the LCS are `removed`; `after` lines absent are `added`; shared
 * lines are `unchanged`. Stable and deterministic.
 */
export function lineDiff(before: string, after: string): LineDiff {
  // An empty body is zero lines (not one phantom blank), so an empty current
  // body diffs as all-added rather than a spurious "removed blank line".
  const a = before ? before.split('\n') : [];
  const b = after ? after.split('\n') : [];
  const n = a.length;
  const m = b.length;

  // LCS length table (n+1 × m+1).
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }

  const rows: DiffRow[] = [];
  const summary: DiffSummary = { added: 0, removed: 0, unchanged: 0 };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      rows.push({ type: 'unchanged', text: a[i] });
      summary.unchanged++;
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      rows.push({ type: 'removed', text: a[i] });
      summary.removed++;
      i++;
    } else {
      rows.push({ type: 'added', text: b[j] });
      summary.added++;
      j++;
    }
  }
  for (; i < n; i++) {
    rows.push({ type: 'removed', text: a[i] });
    summary.removed++;
  }
  for (; j < m; j++) {
    rows.push({ type: 'added', text: b[j] });
    summary.added++;
  }
  return { rows, summary };
}
