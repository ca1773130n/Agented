/**
 * `ag qa` — random-click QA over the running app, via mischief.
 *
 * THE ONE THING THIS MUST NOT DO IS SWALLOW EXIT 3.
 *
 *   0  clean
 *   1  HIGH findings
 *   2  CRITICAL findings
 *   3  the harness failed, OR it could not prove it tested what it claimed
 *
 * 3 exists because the predecessor returned 1 for both "crashed" and "found real
 * bugs", so CI could not tell a broken runner from a broken app. A 3 means the
 * report is not evidence of anything — so it is passed through verbatim and
 * called out, never folded into "some failures".
 */

import { spawn } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { note, out, json, isTTY } from '../lib/output.ts';
import { str, bool, num, UsageError, type Args } from '../lib/args.ts';

/** Repo frontend/ dir — mischief's config, node_modules and reports live there. */
function frontendDir(): string {
  // cli/commands/qa.ts -> ../../frontend
  return join(new URL('../..', import.meta.url).pathname, 'frontend');
}

const EXIT_MEANING: Record<number, string> = {
  0: 'clean',
  1: 'HIGH findings',
  2: 'CRITICAL findings',
  3: 'UNVERIFIED — the harness failed, or could not prove it tested what it claimed',
};

export async function qaCmd(a: Args): Promise<number> {
  const dir = frontendDir();
  if (!existsSync(join(dir, 'node_modules', '.bin', 'mischief'))) {
    note(`mischief is not installed.\n  cd ${dir} && npm i -D mischief`);
    return 2;
  }
  if (!existsSync(join(dir, 'mischief.config.mjs'))) {
    note(`no mischief.config.mjs in ${dir}. Run: cd ${dir} && npx mischief init`);
    return 2;
  }

  const sub = a.positionals[1];
  const argv: string[] = [];

  if (sub === 'replay') {
    const runId = a.positionals[2];
    if (!runId) throw new UsageError('ag qa replay <runId>');
    argv.push('replay', runId);
  } else {
    // `--seed` makes a finding reproducible; without one mischief picks its own
    // and prints it. Surfacing that is the difference between a bug report and
    // an anecdote.
    const seed = str(a, 'seed');
    if (seed) argv.push('--seed', seed);
    const routes = str(a, 'routes');
    if (routes) argv.push('--routes', routes);
    if (bool(a, 'headed')) argv.push('--headed');
  }

  // NEVER pass --allow-prod through. The allowlist is fail-closed for a reason:
  // two mutators write, and the destructive-click guard reads visible labels, so
  // an icon-only delete is invisible to it. Reaching prod is the one flag that
  // can cause real damage, so it is not reachable from this CLI at all.
  if (bool(a, 'allow-prod')) {
    note(
      'refusing --allow-prod: `ag qa` only ever targets localhost.\n' +
        '  mischief WRITES (form submits, file uploads) and its destructive-click\n' +
        '  guard matches visible labels, so an icon-only delete button is invisible\n' +
        '  to it. If you truly mean it, run mischief directly and own that choice.',
    );
    return 2;
  }

  note(`mischief ${argv.join(' ') || '(default run)'}  [cwd ${dir}]`);

  // Snapshot the run dirs so the new one can be identified afterwards. See
  // the crash check below for why this matters.
  const before = runDirs(dir);

  let code = await run(join(dir, 'node_modules', '.bin', 'mischief'), argv, dir);

  // A CRASHED HARNESS MUST NOT READ AS FINDINGS — the whole reason 3 exists.
  //
  // The exit code alone cannot tell the two apart: an uncaught throw inside
  // mischief exits 1 because that is node's code for an unhandled exception,
  // which is the same 1 mischief itself uses for HIGH findings. So on the
  // first live run against the app, a config type error on route 1 of 24 was
  // reported as "exit 1 — HIGH findings", which is precisely the predecessor
  // behaviour this file was written to eliminate.
  //
  // A completed run always writes reports/<runId>/log.json (mischief's
  // report/index.mjs); a crash leaves the directory holding only shots/. That
  // file IS the proof of coverage, so its absence is the definition of 3.
  //
  // Replay is exempt: it re-runs a recorded run and is not required to open a
  // new run directory, so applying this to it would manufacture a false 3.
  if (sub !== 'replay' && code !== 0 && code !== 3 && !wroteLog(dir, before)) {
    note(
      `\nmischief exited ${code} but wrote no reports/<runId>/log.json — it crashed\n` +
        '  rather than finishing. Reporting 3 (unverified) instead: there is no\n' +
        '  findings list to believe, and calling that "findings" is the exact\n' +
        '  confusion this command exists to prevent.',
    );
    code = 3;
  }

  const meaning = EXIT_MEANING[code] ?? `exit ${code}`;

  if (bool(a, 'json')) {
    json({ exit_code: code, meaning, reports: join(dir, 'reports') });
  } else if (code === 3) {
    note(
      `\nexit 3 — ${meaning}.\n` +
        '  This is NOT a pass and NOT a normal failure: the findings list means\n' +
        '  nothing because coverage could not be proven. Common causes: no route\n' +
        '  offered a clickable candidate, or every step was a no-op (a database too\n' +
        '  thin to click). Seed data until it stops exiting 3 — that is exactly\n' +
        '  enough data. Do not disable the guardrails to make it green.',
    );
  } else {
    note(`\nexit ${code} — ${meaning}. Reports: ${join(dir, 'reports')} (parse the JSON, not the markdown)`);
  }
  return code;
}

/** Names of the run directories under frontend/reports/, or [] if there are none. */
function runDirs(dir: string): string[] {
  const reports = join(dir, 'reports');
  if (!existsSync(reports)) return [];
  try {
    return readdirSync(reports, { withFileTypes: true })
      .filter((e) => e.isDirectory())
      .map((e) => e.name);
  } catch {
    return [];
  }
}

/** Did this invocation open a run directory and finish writing its log.json? */
function wroteLog(dir: string, before: string[]): boolean {
  const seen = new Set(before);
  return runDirs(dir).some(
    (name) => !seen.has(name) && existsSync(join(dir, 'reports', name, 'log.json')),
  );
}

function run(cmd: string, args: string[], cwd: string): Promise<number> {
  return new Promise((resolve) => {
    // inherit: mischief's own progress goes straight to the terminal. Its exit
    // code is the product here, not its stdout.
    const child = spawn(cmd, args, { cwd, stdio: 'inherit' });
    child.on('close', (code) => resolve(code ?? 3));
    child.on('error', () => resolve(3));
  });
}

export { EXIT_MEANING, runDirs, wroteLog };
