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
import {
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
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

  // Claimed BEFORE announcing the command: a refused run that has already
  // printed "mischief …" reads as a run that started and then died.
  //
  // Two runs sharing a reports/ directory cannot be told apart: run ids are
  // second-precise, so runs starting in the same second get the SAME directory
  // and the same runId, and no amount of inspecting the output distinguishes
  // them. A run whose json reporter failed could then be proven by the other's
  // log. Rather than keep inventing heuristics for that, refuse to overlap.
  const lock = acquireLock(dir);
  if (!lock) {
    note(
      '\nanother `ag qa` is already running against this reports/ directory.\n' +
        '  Two runs there cannot be told apart — mischief run ids are precise to\n' +
        '  the second, so a same-second pair shares a directory and an id. Wait\n' +
        '  for the other run, or point this one at a different report.outDir.',
    );
    return 3;
  }

  note(`mischief ${argv.join(' ') || '(default run)'}  [cwd ${dir}]`);

  // Floor to the second: mischief's run ids are second-precise, and some
  // filesystems store mtimes at that granularity too. See provenLog().
  const startedAt = Math.floor(Date.now() / 1000) * 1000;
  let rawCode: number;
  let stdout: string;
  try {
    ({ code: rawCode, stdout } = await run(
      join(dir, 'node_modules', '.bin', 'mischief'),
      argv,
      dir,
      bool(a, 'json'),
    ));
  } finally {
    lock.release();
  }

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
  const runDir = reportedRunDir(stdout, dir);
  const proof = provenLog(runDir, startedAt);
  const code = resolveExit(rawCode, proof);
  if (code !== rawCode) {
    note(
      proof === 'no-report'
        ? `\nmischief exited ${rawCode} but named no single report — it did not finish, or\n` +
            '  printed more than one REPORT: line, which cannot be attributed.\n' +
            '  Reporting 3 (unverified) instead: there is no findings list to believe,\n' +
            '  and calling that "findings" — or "clean" — is the exact confusion this\n' +
            '  command exists to prevent.\n' +
            '  (`ag qa` needs the markdown + json reporters; a config that disables\n' +
            '  them removes the only proof that a run happened.)'
        : proof === 'stale'
          ? `\nmischief exited ${rawCode} and named ${runDir}, but the log.json there\n` +
            '  predates this run — it belongs to an earlier run that happened to get the\n' +
            '  same second-precise run id. This run produced no log of its own, so it is\n' +
            '  3 (unverified) rather than a verdict read off somebody else’s data.'
          : proof === 'corrupt'
            ? `\nmischief exited ${rawCode} and named ${runDir}, but the log.json there does\n` +
              '  not parse, or names a different run. A reporter that opened the file and\n' +
              '  then failed leaves exactly this. `ag qa` tells you to parse that file, so\n' +
              '  a file that cannot be parsed is 3 (unverified), not a verdict.'
            : `\nmischief exited ${rawCode} and named a report, but ${proof === 'no-log' ? 'no log.json sits beside it' : 'that path could not be read'}.\n` +
              '  The markdown is a rendering; log.json is the data. Without it there is\n' +
              '  nothing to parse, so this is 3 (unverified), not a verdict.',
    );
  }

  const meaning = EXIT_MEANING[code] ?? `exit ${code}`;
  // Report the directory the child actually used, not a guess. A configured
  // `report.outDir` sends output somewhere else entirely, and printing
  // frontend/reports then sends the reader to an empty directory.
  const where = runDir ?? join(dir, 'reports');

  if (bool(a, 'json')) {
    json({ exit_code: code, meaning, reports: where });
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
    note(`\nexit ${code} — ${meaning}. Reports: ${where} (parse the JSON, not the markdown)`);
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
  const found = stdout
    .split('\n')
    .map((line) => /^REPORT:\s*(.+?)\s*$/.exec(line))
    .filter((m): m is RegExpExecArray => m !== null)
    .map((m) => m[1]);
  // More than one sentinel is not "the last one wins" — it is a signal we
  // cannot read. A report path containing a literal "\nREPORT: " would forge a
  // second line and steer this at another run's directory, and nothing else
  // legitimately prints two. Refuse rather than pick.
  if (found.length !== 1) return null;
  const md = isAbsolute(found[0]) ? found[0] : join(dir, found[0]);
  return join(dirname(md), basename(md, '.md'));
}

/**
 * Is there a parseable report in the directory the child named, and is it from
 * THIS run?
 *
 * 'proven'    — log.json is there and was written during our window. That IS
 *               the evidence `ag qa` reports on.
 * 'no-report' — the child never named a directory: it did not finish.
 * 'no-log'    — it named one, but only the markdown rendering landed. The
 *               markdown is for humans; log.json is the data, and without it
 *               there is nothing to parse.
 * 'stale'     — the log there predates us. Run ids are only second-precise
 *               (mischief's util.mjs makeRunId), so two runs started in the
 *               same second share a directory; a run whose json reporter failed
 *               would otherwise be "proven" by the earlier run's log. The mtime
 *               is NOT identity here — the child already told us the path — it
 *               is only a freshness assertion on top of it.
 * 'unreadable'— the path exists but cannot be stat'd.
 */
function provenLog(
  runDir: string | null,
  startedAt: number,
): 'proven' | 'no-report' | 'no-log' | 'stale' | 'corrupt' | 'unreadable' {
  if (!runDir) return 'no-report';
  const log = join(runDir, 'log.json');
  let raw: string;
  let mtimeMs: number;
  try {
    const s = statSync(log);
    if (!s.isFile()) return 'no-log';
    // Read it, but not at any size. Only a small prefix is actually needed, and
    // slurping an arbitrarily large file to answer a yes/no question is how a
    // verification step becomes the thing that falls over.
    if (s.size > MAX_LOG_BYTES) return 'unreadable';
    mtimeMs = s.mtimeMs;
    raw = readFileSync(log, 'utf8');
  } catch (e) {
    return (e as NodeJS.ErrnoException)?.code === 'ENOENT' ? 'no-log' : 'unreadable';
  }
  // Existence is not evidence. A reporter that opened the file and then failed
  // — out of disk, killed mid-write — leaves a truncated log that is present,
  // current, and unparseable. Since `ag qa` tells its caller to parse this
  // file, the least it can do is confirm that parsing works.
  let parsed: { runId?: unknown };
  try {
    parsed = JSON.parse(raw);
  } catch {
    return 'corrupt';
  }
  // The log names its own run (report/index.mjs writes runId first). It must be
  // the run whose directory it sits in, or this is somebody else's data.
  if (parsed?.runId !== basename(runDir)) return 'corrupt';
  return mtimeMs >= startedAt ? 'proven' : 'stale';
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

/**
 * Only the tail is kept — a long run with a chatty custom reporter should not
 * grow this process without limit. The bound is in LINES, not characters:
 * slicing a character window can cut through the sentinel itself (`REPORT: …`
 * straddling the boundary reads as no sentinel at all, turning a healthy run
 * into an exit 3), and a character count is not a memory bound anyway once the
 * output is multibyte.
 */
const STDOUT_TAIL_LINES = 200;

/**
 * Ceiling on the log we will read to verify a run. Generous next to a real one
 * (a 24-route run here produced ~35 KB) and far below what would hurt.
 */
const MAX_LOG_BYTES = 256 * 1024 * 1024;

/** Trim accumulated output to the last N whole lines, sentinel intact. */
function keepTail(text: string): string {
  return text.split('\n').slice(-STDOUT_TAIL_LINES).join('\n');
}

/**
 * Exclusive claim on a reports/ directory, so two runs cannot interleave in it.
 *
 * `wx` is create-or-fail in one syscall, which is the whole mechanism — no
 * check-then-create window. The pid is written so a lock left behind by a
 * killed run can be told from a live one and taken over; otherwise a single
 * crash would wedge the command until someone deleted a file they had never
 * heard of. Returns null when another LIVE run holds it.
 */
function acquireLock(dir: string): { release: () => void } | null {
  const reports = join(dir, 'reports');
  mkdirSync(reports, { recursive: true });
  const lockPath = join(reports, '.ag-qa.lock');
  const claim = () => {
    const fd = openSync(lockPath, 'wx');
    writeFileSync(fd, String(process.pid));
    closeSync(fd);
    return {
      release: () => {
        try {
          unlinkSync(lockPath);
        } catch {
          // Already gone: nothing to release, and failing here would turn a
          // finished run into an error.
        }
      },
    };
  };
  try {
    return claim();
  } catch (e) {
    if ((e as NodeJS.ErrnoException)?.code !== 'EEXIST') throw e;
  }
  const holder = Number(readFileSync(lockPath, 'utf8').trim());
  if (Number.isInteger(holder) && holder > 0 && isAlive(holder)) return null;
  // Stale. Clear it and claim; if someone beat us to that, they hold it.
  try {
    unlinkSync(lockPath);
    return claim();
  } catch {
    return null;
  }
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0); // signal 0 tests for existence, sends nothing
    return true;
  } catch (e) {
    // EPERM means it exists and belongs to someone else.
    return (e as NodeJS.ErrnoException)?.code === 'EPERM';
  }
}

function run(
  cmd: string,
  args: string[],
  cwd: string,
  jsonMode: boolean,
): Promise<{ code: number; stdout: string }> {
  return new Promise((resolve) => {
    // stdout is piped rather than inherited so the child's `REPORT:` line can
    // be read, then written straight through so its progress still streams
    // live. mischief formats no differently off a TTY (no isTTY checks in its
    // source), so nothing is lost by piping. stderr stays inherited.
    //
    // Under --json the child's narration goes to STDERR instead: this command's
    // stdout must be a single parseable object, and `ag qa --json | jq` was
    // being fed mischief's progress lines first.
    const echo = jsonMode ? process.stderr : process.stdout;
    const child = spawn(cmd, args, { cwd, stdio: ['inherit', 'pipe', 'inherit'] });
    let stdout = '';
    child.stdout?.setEncoding('utf8');
    child.stdout?.on('data', (chunk: string) => {
      // Whole lines only. A trailing partial line is kept as-is — the sentinel
      // arrives last and may still be mid-flight when a chunk ends.
      stdout = keepTail(stdout + chunk);
      echo.write(chunk);
    });
    child.on('close', (code) => resolve({ code: code ?? 3, stdout }));
    child.on('error', () => resolve({ code: 3, stdout }));
  });
}

export { acquireLock, EXIT_MEANING, keepTail, provenLog, reportedRunDir, resolveExit };
