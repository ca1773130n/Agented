/**
 * Output discipline, enforced in one place.
 *
 * THE RULE: **stdout is data, stderr is narration.** Every progress message,
 * spinner, warning and error goes to stderr; only the thing a caller would want
 * to capture goes to stdout. That is what makes `ID=$(ag product new X)` and
 * `ag product ls --json | jq` safe, and it is why an agent can drive this CLI
 * without parsing around chatter.
 */

export const isTTY = process.stdout.isTTY === true;

/** Data. The only function that writes to stdout. */
export function out(s: string): void {
  process.stdout.write(s.endsWith('\n') ? s : s + '\n');
}

/** Narration: progress, hints, warnings. Never captured by `$(…)`. */
export function note(s: string): void {
  process.stderr.write(s.endsWith('\n') ? s : s + '\n');
}

export function json(value: unknown): void {
  out(JSON.stringify(value, null, isTTY ? 2 : 0));
}

/** Bare scalar on stdout — the `$(…)`-composable form. */
export function scalar(v: string | number): void {
  out(String(v));
}

/**
 * A plain aligned table. Deliberately not boxed: piping it through `awk` or
 * `cut` should stay trivial, so columns are separated by two spaces and nothing
 * else.
 */
export function table(rows: Record<string, unknown>[], columns?: string[]): void {
  if (!rows.length) {
    note('(none)');
    return;
  }
  const cols = columns ?? Object.keys(rows[0]);
  const cell = (r: Record<string, unknown>, c: string) => {
    const v = r[c];
    if (v === null || v === undefined) return '';
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  };
  const widths = cols.map((c) => Math.max(c.length, ...rows.map((r) => cell(r, c).length)));
  const line = (cells: string[]) =>
    cells.map((s, i) => (i === cells.length - 1 ? s : s.padEnd(widths[i]))).join('  ');
  note(line(cols.map((c) => c.toUpperCase())));
  for (const r of rows) out(line(cols.map((c) => cell(r, c))));
}

/** Key/value block for a single record. */
export function kv(obj: Record<string, unknown>, keys?: string[]): void {
  const ks = keys ?? Object.keys(obj);
  const w = Math.max(...ks.map((k) => k.length));
  for (const k of ks) {
    const v = obj[k];
    if (v === undefined) continue;
    out(`${k.padEnd(w)}  ${v === null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v)}`);
  }
}

/**
 * Unwrap the common list envelopes so `--json` yields a bare array that `jq`
 * can index directly. The backend returns `{products: [...], total_count: n}`,
 * `{projects: [...]}`, `{items: [...]}` and friends; a caller should not have to
 * know which key this particular route chose.
 */
export function unwrapList(body: unknown): unknown {
  if (Array.isArray(body)) return body;
  if (body && typeof body === 'object') {
    const o = body as Record<string, unknown>;
    const arrays = Object.entries(o).filter(([, v]) => Array.isArray(v));
    if (arrays.length === 1) return arrays[0][1];
  }
  return body;
}
