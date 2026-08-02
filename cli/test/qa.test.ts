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
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { EXIT_MEANING, provenLog, reportedRunDir, resolveExit } from '../commands/qa.ts';

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
function runDir(dir: string, id: string, withLog: boolean): string {
  mkdirSync(join(dir, id), { recursive: true });
  writeFileSync(join(dir, `${id}.md`), '# report');
  if (withLog) writeFileSync(join(dir, id, 'log.json'), '{"pages":[]}');
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
  assert.equal(provenLog(null), 'no-report');
  assert.equal(resolveExit(1, provenLog(null)), 3);
});

test('a relative REPORT path is anchored to the frontend dir', () => {
  assert.equal(reportedRunDir('REPORT: reports/r1.md\n', '/frontend'), '/frontend/reports/r1');
});

test('the last REPORT line wins', () => {
  const out = 'REPORT: /a/one.md\nREPORT: /a/two.md\n';
  assert.equal(reportedRunDir(out, '/frontend'), '/a/two');
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
    assert.equal(provenLog(reportedRunDir(stdout, dir)), 'proven');
  });
});

// ---- is there anything to parse --------------------------------------------

test('a finished run is proven by its log.json', () => {
  withTmp((dir) => {
    const md = runDir(dir, '20260802-114440', true);
    assert.equal(provenLog(reportedRunDir(`REPORT: ${md}\n`, dir)), 'proven');
  });
});

test('markdown without log.json is not proof', () => {
  // The markdown is a rendering; log.json is the data the command tells you to
  // parse. A run that produced only the rendering has nothing to report on.
  withTmp((dir) => {
    const md = runDir(dir, '20260802-114440', false);
    assert.equal(provenLog(reportedRunDir(`REPORT: ${md}\n`, dir)), 'no-log');
  });
});

test('a named directory that does not exist is not proof', () => {
  withTmp((dir) => assert.equal(provenLog(join(dir, 'never-created')), 'no-log'));
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
