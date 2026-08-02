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
import { existsSync, readdirSync, statSync } from 'node:fs';
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

  // Fingerprint the existing logs so THIS run's can be identified afterwards.
  // See the proof check below.
  const before = logFingerprints(dir);

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
  // file IS the proof, so demand it for EVERY outcome — 0 included. "Clean"
  // is the claim that most needs evidence: a green with nothing behind it is
  // worse than a red, and exit 0 is reachable with an unwritten report.
  //
  // Replay is NOT exempt. It resolves the old run's seed/routes/steps and
  // calls runMonkey exactly like a fresh run (mischief's bin: replayOverrides
  // -> runMonkey), so it opens its own run directory and owes the same proof.
  const proof = provenLog(dir, before);
  if (resolveExit(code, proof) !== code) {
    note(
      proof === 'ambiguous'
        ? `\nmischief exited ${code}, but more than one report was written while it ran.\n` +
            '  This run cannot be told apart from a concurrent one, so its findings\n' +
            '  cannot be attributed. Reporting 3 (unverified). Run `ag qa` one at a\n' +
            '  time against a given reports/ directory.'
        : `\nmischief exited ${code} but wrote no reports/<runId>/log.json — it did not\n` +
            '  finish. Reporting 3 (unverified) instead: there is no findings list to\n' +
            '  believe, and calling that "findings" — or "clean" — is the exact\n' +
            '  confusion this command exists to prevent.',
    );
  }
  code = resolveExit(code, proof);

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

/**
 * Every `reports/<runId>/log.json` that exists, mapped to its mtime.
 *
 * Identity comes from the mtime, NOT from the directory name. A run id is only
 * second-precise (`makeRunId` in mischief's util.mjs), so names can repeat, and
 * a name-diff also cannot tell "this run wrote it" from "some other run did".
 * A log whose mtime changed is unambiguously written during our window.
 *
 * `statSync` follows symlinks, unlike `Dirent.isDirectory()` — a symlinked run
 * directory is a real report and must not read as a missing one.
 */
function logFingerprints(dir: string): Map<string, number> {
  const reports = join(dir, 'reports');
  const out = new Map<string, number>();
  if (!existsSync(reports)) return out;
  try {
    for (const name of readdirSync(reports)) {
      const log = join(reports, name, 'log.json');
      try {
        const s = statSync(log);
        if (s.isFile()) out.set(log, s.mtimeMs);
      } catch {
        // Not a run directory, or unreadable. Either way it is not evidence.
      }
    }
  } catch {
    // reports/ unreadable — no evidence available, which the caller reads as
    // "not proven" rather than as a pass.
  }
  return out;
}

/**
 * Did THIS invocation finish writing a report?
 *
 * 'proven'    — exactly one log.json appeared or changed. That one is ours.
 * 'missing'   — none did. The run did not finish, whatever it exited with.
 * 'ambiguous' — several did, so a concurrent run is in play and this run's
 *               findings cannot be attributed to it. Deliberately NOT treated
 *               as proof: guessing which is ours is how a crash gets reported
 *               as somebody else's findings.
 */
function provenLog(dir: string, before: Map<string, number>): 'proven' | 'missing' | 'ambiguous' {
  const fresh = [...logFingerprints(dir)].filter(([p, m]) => before.get(p) !== m);
  if (fresh.length === 1) return 'proven';
  return fresh.length === 0 ? 'missing' : 'ambiguous';
}

/**
 * The whole policy, in one place so it can be checked as a truth table.
 *
 * Every outcome owes proof, including 0. "Clean" is the claim that most needs
 * evidence — an unverified green is worse than an unverified red, because
 * nobody goes looking behind it. mischief's own 3 is passed through untouched:
 * it already means unverified, and it carries a better reason than we could.
 */
function resolveExit(code: number, proof: 'proven' | 'missing' | 'ambiguous'): number {
  if (code === 3) return 3;
  return proof === 'proven' ? code : 3;
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

export { EXIT_MEANING, logFingerprints, provenLog, resolveExit };
