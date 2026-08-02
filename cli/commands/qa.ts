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
import { existsSync, statSync } from 'node:fs';
import { basename, dirname, isAbsolute, join } from 'node:path';
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

  const { code: rawCode, stdout } = await run(
    join(dir, 'node_modules', '.bin', 'mischief'),
    argv,
    dir,
  );

  // A CRASHED HARNESS MUST NOT READ AS FINDINGS — the whole reason 3 exists.
  //
  // The exit code alone cannot tell the two apart: an uncaught throw inside
  // mischief exits 1 because that is node's code for an unhandled exception,
  // which is the same 1 mischief itself uses for HIGH findings. So on the
  // first live run against the app, a config type error on route 1 of 24 was
  // reported as "exit 1 — HIGH findings", which is precisely the predecessor
  // behaviour this file was written to eliminate.
  //
  // Proof is demanded for EVERY outcome, 0 included. "Clean" is the claim that
  // most needs evidence: a green nobody looks behind is worse than a red.
  //
  // Replay is NOT exempt. It resolves the old run's seed/routes/steps and calls
  // runMonkey exactly like a fresh run (mischief's bin: replayOverrides ->
  // runMonkey), so it opens its own run directory and owes the same proof.
  //
  // Ownership comes from the CHILD, via the `REPORT:` line it prints, and never
  // from scanning reports/. Two earlier attempts scanned: by directory name,
  // then by log.json mtime. Both were unsound for the same reason — with a
  // concurrent run in the same directory, "a new report appeared" is not
  // evidence that THIS run wrote it, so a crashed run could be credited with a
  // healthy one's findings. A path the child itself reports cannot be confused
  // with someone else's, and it also follows a configured `report.outDir`,
  // which a hardcoded reports/ scan silently missed.
  const proof = provenLog(reportedRunDir(stdout, dir));
  let code = resolveExit(rawCode, proof);
  if (code !== rawCode) {
    note(
      proof === 'no-report'
        ? `\nmischief exited ${rawCode} but printed no REPORT: line — it did not finish.\n` +
            '  Reporting 3 (unverified) instead: there is no findings list to believe,\n' +
            '  and calling that "findings" — or "clean" — is the exact confusion this\n' +
            '  command exists to prevent.\n' +
            '  (`ag qa` needs the markdown + json reporters; a config that disables\n' +
            '  them removes the only proof that a run happened.)'
        : `\nmischief exited ${rawCode} and named a report, but ${proof === 'no-log' ? 'no log.json sits beside it' : 'that path is unreadable'}.\n` +
            '  The markdown is a rendering; log.json is the data. Without it there is\n' +
            '  nothing to parse, so this is 3 (unverified), not a verdict.',
    );
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

/**
 * The run directory THIS invocation wrote, taken from the child's own
 * `REPORT: <path>` line (mischief's bin prints it last, after the summary).
 *
 * The last match wins: nothing else prints that prefix, but a run's own output
 * could in principle be echoed by page content, and the child's final line is
 * the authoritative one.
 *
 * Returns null when no such line was printed, which means the run did not reach
 * its reporting stage. `report.outDir` is resolved to an absolute path by
 * mischief's config, but a relative one is anchored to the frontend dir rather
 * than assumed.
 *
 * The two reporters do NOT write to the same place: markdown lands at
 * `<outDir>/<runId>.md` and the log at `<outDir>/<runId>/log.json`
 * (report/index.mjs:23 and :37). So the run directory is the md path's
 * basename-minus-extension, NOT its dirname — taking the dirname yields
 * `<outDir>` and reports every healthy run as unproven.
 */
function reportedRunDir(stdout: string, dir: string): string | null {
  let found: string | null = null;
  for (const line of stdout.split('\n')) {
    const m = /^REPORT:\s*(.+?)\s*$/.exec(line);
    if (m) found = m[1];
  }
  if (!found) return null;
  const md = isAbsolute(found) ? found : join(dir, found);
  return join(dirname(md), basename(md, '.md'));
}

/**
 * Is there a parseable report in the directory the child named?
 *
 * 'proven'    — log.json is there. That IS the evidence `ag qa` reports on.
 * 'no-report' — the child never named a directory: it did not finish.
 * 'no-log'    — it named one, but only the markdown rendering landed. The
 *               markdown is for humans; log.json is the data, and without it
 *               there is nothing to parse.
 * 'unreadable'— the path exists but cannot be stat'd.
 */
function provenLog(runDir: string | null): 'proven' | 'no-report' | 'no-log' | 'unreadable' {
  if (!runDir) return 'no-report';
  try {
    return statSync(join(runDir, 'log.json')).isFile() ? 'proven' : 'no-log';
  } catch (e) {
    return (e as NodeJS.ErrnoException)?.code === 'ENOENT' ? 'no-log' : 'unreadable';
  }
}

/**
 * The whole policy, in one place so it can be checked as a truth table.
 *
 * Every outcome owes proof, including 0. "Clean" is the claim that most needs
 * evidence — an unverified green is worse than an unverified red, because
 * nobody goes looking behind it. mischief's own 3 is passed through untouched:
 * it already means unverified, and it carries a better reason than we could.
 */
function resolveExit(code: number, proof: ReturnType<typeof provenLog>): number {
  if (code === 3) return 3;
  return proof === 'proven' ? code : 3;
}

function run(cmd: string, args: string[], cwd: string): Promise<{ code: number; stdout: string }> {
  return new Promise((resolve) => {
    // stdout is piped rather than inherited so the child's `REPORT:` line can
    // be read, then written straight through so its progress still streams
    // live. mischief formats no differently off a TTY (no isTTY checks in its
    // source), so nothing is lost by piping. stderr stays inherited.
    const child = spawn(cmd, args, { cwd, stdio: ['inherit', 'pipe', 'inherit'] });
    let stdout = '';
    child.stdout?.setEncoding('utf8');
    child.stdout?.on('data', (chunk: string) => {
      stdout += chunk;
      process.stdout.write(chunk);
    });
    child.on('close', (code) => resolve({ code: code ?? 3, stdout }));
    child.on('error', () => resolve({ code: 3, stdout }));
  });
}

export { EXIT_MEANING, provenLog, reportedRunDir, resolveExit };
