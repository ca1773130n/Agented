/**
 * Unit tests for `ag qa`'s report-proof check.
 *
 * The command's contract is that exit 3 means "the report is not evidence of
 * anything". The first live run against the app broke it: mischief threw on
 * route 1 of 24, node exited 1 for the uncaught exception, and `ag qa` printed
 * "exit 1 — HIGH findings" for a run that had tested nothing.
 *
 * Ownership of a report comes from the CHILD's `REPORT:` line, never from
 * scanning reports/. Two earlier attempts scanned — by directory name, then by
 * log.json mtime — and both were unsound: with a concurrent run writing to the
 * same directory, "a new report appeared" does not mean THIS run wrote it, so a
 * crash could be credited with someone else's findings.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
  acquireLock,
  EXIT_MEANING,
  keepTail,
  provenLog,
  reportedRunDir,
  resolveExit,
} from '../commands/qa.ts';

function withTmp(fn: (dir: string) => void) {
  // NB: this repo sets TMPDIR to the project root, so fixtures land inside it.
  // The finally-clean is what keeps them from becoming committed litter.
  const dir = mkdtempSync(join(tmpdir(), 'ag-qa-'));
  try {
    fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * A finished run, laid out the way mischief actually lays one out: the markdown
 * at <outDir>/<id>.md and the log at <outDir>/<id>/log.json — siblings, not
 * nested (report/index.mjs:23 and :37). Returns the md path the child reports.
 */
function runDir(dir: string, id: string, log: boolean | string): string {
  mkdirSync(join(dir, id), { recursive: true });
  writeFileSync(join(dir, `${id}.md`), '# report');
  if (log !== false) {
    // A real log names its own run first (report/index.mjs), which is what
    // proves it belongs to the directory it sits in.
    writeFileSync(
      join(dir, id, 'log.json'),
      typeof log === 'string' ? log : JSON.stringify({ runId: id, pages: [] }),
    );
  }
  return join(dir, `${id}.md`);
}

// ---- whose report is it -----------------------------------------------------

test('the run directory comes from the child, not from the filesystem', () => {
  const out = 'mischief: route 1/2 /login\nmischief: done — 0 critical\nREPORT: /tmp/r/20260802-114440.md\n';
  assert.equal(reportedRunDir(out, '/frontend'), '/tmp/r/20260802-114440');
});

test('the md is a SIBLING of the run directory, not inside it', () => {
  // Taking dirname(md) yields <outDir> and reports every healthy run as
  // unproven. Caught by replaying a real run's stdout, not by a fixture —
  // the fixture had encoded the same wrong assumption as the code.
  assert.equal(
    reportedRunDir('REPORT: /f/reports/20260802-114440.md\n', '/f'),
    '/f/reports/20260802-114440',
  );
});

test('a concurrent run\'s report cannot be mistaken for ours', () => {
  // The defect that killed two previous designs: run A crashes while run B
  // writes a perfectly good report. Scanning saw "one new report" and credited
  // it to A. Reading A's own output, A named nothing, so A is unverified.
  const crashed = 'mischief: route 1/24 /login\nTypeError: re.test is not a function\n';
  assert.equal(reportedRunDir(crashed, '/frontend'), null);
  assert.equal(provenLog(null, 0), 'no-report');
  assert.equal(resolveExit(1, provenLog(null, 0)), 3);
});

test('a relative REPORT path is anchored to the frontend dir', () => {
  assert.equal(reportedRunDir('REPORT: reports/r1.md\n', '/frontend'), '/frontend/reports/r1');
});

test('two REPORT lines are refused, not resolved by picking one', () => {
  // A report path containing a literal "\nREPORT: " forges a second sentinel;
  // "last one wins" would then steer proof at a directory of the forger's
  // choosing. Nothing legitimate prints two, so ambiguity is unreadable.
  const forged = 'REPORT: /a/real.md\nREPORT: /somewhere/else.md\n';
  assert.equal(reportedRunDir(forged, '/frontend'), null);
  assert.equal(resolveExit(0, provenLog(null, 0)), 3);
});

test('a configured report.outDir is followed, not second-guessed', () => {
  // A hardcoded reports/ scan reported a healthy run as unverified whenever the
  // config pointed the reporter somewhere else.
  assert.equal(reportedRunDir('REPORT: /elsewhere/qa-alt/r9.md\n', '/frontend'), '/elsewhere/qa-alt/r9');
});

test("a REAL run's stdout resolves to a directory that holds its log.json", () => {
  // Replays the exact bytes mischief printed on this machine. A fixture cannot
  // catch a wrong assumption about mischief's own layout; this can.
  withTmp((dir) => {
    const md = runDir(dir, '20260802-114440', true);
    const stdout =
      'mischief: route 24/24 /help\n' +
      'mischief: done — 8 critical, 85 high — NOT VERIFIED (exit 3)\n' +
      `REPORT: ${md}\n`;
    assert.equal(provenLog(reportedRunDir(stdout, dir), 0), 'proven');
  });
});

// ---- is there anything to parse --------------------------------------------

test('a finished run is proven by its log.json', () => {
  withTmp((dir) => {
    const md = runDir(dir, '20260802-114440', true);
    assert.equal(provenLog(reportedRunDir(`REPORT: ${md}\n`, dir), 0), 'proven');
  });
});

test('markdown without log.json is not proof', () => {
  // The markdown is a rendering; log.json is the data the command tells you to
  // parse. A run that produced only the rendering has nothing to report on.
  withTmp((dir) => {
    const md = runDir(dir, '20260802-114440', false);
    assert.equal(provenLog(reportedRunDir(`REPORT: ${md}\n`, dir), 0), 'no-log');
  });
});

test('a named directory that does not exist is not proof', () => {
  withTmp((dir) => assert.equal(provenLog(join(dir, 'never-created'), 0), 'no-log'));
});

test("an EARLIER run's log at the same path does not prove this one", () => {
  // Run ids are second-precise, so two runs started in the same second share a
  // directory. A run whose json reporter failed would otherwise be "proven" by
  // the older run's log sitting there. The child named the path; the mtime only
  // asserts freshness on top of that.
  withTmp((dir) => {
    const md = runDir(dir, '20260802-114440', true);
    const startedAfterTheLogWasWritten = Date.now() + 60_000;
    assert.equal(
      provenLog(reportedRunDir(`REPORT: ${md}\n`, dir), startedAfterTheLogWasWritten),
      'stale',
    );
    assert.equal(resolveExit(0, 'stale'), 3);
  });
});

test('a truncated log is not proof, however fresh it is', () => {
  // A reporter that opened the file then died — out of disk, killed mid-write —
  // leaves a log that exists, is current, and cannot be parsed. `ag qa` tells
  // its caller to parse this file, so the least it can do is confirm it parses.
  withTmp((dir) => {
    const md = runDir(dir, '20260802-114440', '{"runId":"20260802-1144');
    assert.equal(provenLog(reportedRunDir(`REPORT: ${md}\n`, dir), 0), 'corrupt');
    assert.equal(resolveExit(0, 'corrupt'), 3);
  });
});

test("a log belonging to a different run is not proof", () => {
  withTmp((dir) => {
    const md = runDir(dir, '20260802-114440', JSON.stringify({ runId: '20260731-090000' }));
    assert.equal(provenLog(reportedRunDir(`REPORT: ${md}\n`, dir), 0), 'corrupt');
  });
});

test('mischief still writes reports where this command looks for them', () => {
  // A contract canary. Every other test here agrees with qa.ts by construction,
  // so none of them would notice mischief moving its output — which is exactly
  // the mistake that shipped once already. This reads the installed package and
  // fails when the layout it encodes changes.
  const src = readFileSync(
    join(import.meta.dirname, '..', '..', 'frontend', 'node_modules', 'mischief', 'src', 'report', 'index.mjs'),
    'utf8',
  );
  assert.match(src, /path\.join\(outDir, `\$\{runId\}\.md`\)/, 'markdown is <outDir>/<runId>.md');
  assert.match(src, /path\.join\(outDir, runId, 'log\.json'\)/, 'log is <outDir>/<runId>/log.json');
  // And that the log still names its own run, which is what provenLog checks.
  assert.match(src, /JSON\.stringify\(\s*\{\s*runId,/, 'log.json starts with runId');
});

test('the kept tail cannot slice through the sentinel', () => {
  // A character-window tail could cut "REPORT: /x.md" in half at the boundary,
  // which reads as no sentinel and turns a healthy run into exit 3. Whole lines
  // only, so the last line always survives intact.
  const noise = Array.from({ length: 5000 }, (_, i) => `mischief: step ${i} ${'x'.repeat(200)}`);
  const stdout = keepTail([...noise, 'REPORT: /a/r1.md'].join('\n'));
  assert.equal(reportedRunDir(stdout, '/frontend'), '/a/r1');
});

// ---- one run at a time ------------------------------------------------------

test('a second run cannot start against the same reports/ directory', () => {
  // Two runs sharing reports/ cannot be told apart: run ids are second-precise,
  // so a same-second pair gets the same directory AND the same id, and no
  // inspection of the output separates them. Refusing to overlap is what makes
  // the proof check sound rather than probabilistic.
  withTmp((dir) => {
    const first = acquireLock(dir);
    assert.ok(first, 'first run takes the lock');
    assert.equal(acquireLock(dir), null, 'second run is refused');
    first!.release();
    const third = acquireLock(dir);
    assert.ok(third, 'released lock is available again');
    third!.release();
  });
});

test('a lock left by a dead run is taken over, not obeyed forever', () => {
  // Otherwise one crash wedges the command until someone deletes a file they
  // have never heard of.
  withTmp((dir) => {
    mkdirSync(join(dir, 'reports'), { recursive: true });
    // pid 2^31-1 is not a running process on any of these platforms.
    writeFileSync(join(dir, 'reports', '.ag-qa.lock'), '2147483647');
    const taken = acquireLock(dir);
    assert.ok(taken, 'stale lock is reclaimed');
    taken!.release();
  });
});

test('a lock held by a LIVE process is respected', () => {
  withTmp((dir) => {
    mkdirSync(join(dir, 'reports'), { recursive: true });
    writeFileSync(join(dir, 'reports', '.ag-qa.lock'), String(process.pid));
    assert.equal(acquireLock(dir), null);
  });
});

test('releasing twice is not an error', () => {
  // The release runs in a finally; a run that fails after an external cleanup
  // must not turn that into a second failure.
  withTmp((dir) => {
    const lock = acquireLock(dir);
    lock!.release();
    assert.doesNotThrow(() => lock!.release());
  });
});

// ---- the policy, as a truth table ------------------------------------------

test('an UNPROVEN clean run is not reported as clean', () => {
  // The dangerous direction: nobody looks behind a green.
  assert.equal(resolveExit(0, 'no-report'), 3);
  assert.equal(resolveExit(0, 'no-log'), 3);
  assert.equal(resolveExit(0, 'unreadable'), 3);
});

test('a proven run keeps its own verdict, whatever it is', () => {
  assert.equal(resolveExit(0, 'proven'), 0);
  assert.equal(resolveExit(1, 'proven'), 1);
  assert.equal(resolveExit(2, 'proven'), 2);
});

test('an unproven findings run is unverified, not findings', () => {
  // The original bug: a crash exits 1 because node does, which is the same 1
  // mischief uses for HIGH findings.
  assert.equal(resolveExit(1, 'no-report'), 3);
  assert.equal(resolveExit(2, 'no-report'), 3);
});

test("mischief's own 3 is passed through untouched", () => {
  // It already means unverified and carries a better reason than we could.
  assert.equal(resolveExit(3, 'proven'), 3);
  assert.equal(resolveExit(3, 'no-report'), 3);
});

test('replay is subject to the same rule as a fresh run', () => {
  // replay resolves the old seed/routes/steps and calls runMonkey exactly like
  // a fresh run, so it opens its own run directory and owes the same proof.
  // Exempting it let a crashed replay report findings.
  assert.equal(resolveExit(1, 'no-report'), 3);
  assert.equal(resolveExit(1, 'proven'), 1);
});

test('3 is documented as unverified, not as a kind of failure', () => {
  assert.match(EXIT_MEANING[3], /UNVERIFIED/);
  assert.notEqual(EXIT_MEANING[1], EXIT_MEANING[3]);
});
