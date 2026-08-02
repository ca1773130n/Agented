/**
 * Unit tests for `ag qa`'s report-proof check.
 *
 * The command's contract is that exit 3 means "the report is not evidence of
 * anything". The first live run against the app broke it: mischief threw on
 * route 1 of 24, node exited 1 for the uncaught exception, and `ag qa` printed
 * "exit 1 — HIGH findings" for a run that had tested nothing.
 *
 * The distinguishing fact is on disk, not in the exit code: a finished run
 * writes reports/<runId>/log.json, a crashed one leaves the directory with only
 * shots/. Identity comes from the mtime rather than the directory name, because
 * a run id is only second-precise and a name-diff cannot tell "we wrote this"
 * from "something else did".
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, utimesSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { EXIT_MEANING, logFingerprints, provenLog, resolveExit } from '../commands/qa.ts';

/** Build a fake frontend/ dir; `runs` maps a run id to whether it finished. */
function fixture(runs: Record<string, boolean> = {}): string {
  const dir = mkdtempSync(join(tmpdir(), 'ag-qa-'));
  for (const [id, finished] of Object.entries(runs)) writeRun(dir, id, finished);
  return dir;
}

/** Create reports/<id>/, with a log.json only if the run "finished". */
function writeRun(dir: string, id: string, finished: boolean, mtime?: number) {
  const run = join(dir, 'reports', id);
  mkdirSync(join(run, 'shots'), { recursive: true });
  if (!finished) return;
  const log = join(run, 'log.json');
  writeFileSync(log, '{"pages":[]}');
  if (mtime !== undefined) utimesSync(log, mtime, mtime);
}

function withFixture(runs: Record<string, boolean>, fn: (dir: string) => void) {
  const dir = fixture(runs);
  try {
    fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test('a crashed run — a run directory with no log.json — is not proven', () => {
  withFixture({}, (dir) => {
    const before = logFingerprints(dir);
    writeRun(dir, '20260802-114121', false);
    assert.equal(provenLog(dir, before), 'missing');
  });
});

test('a finished run is proven', () => {
  withFixture({}, (dir) => {
    const before = logFingerprints(dir);
    writeRun(dir, '20260802-114121', true);
    assert.equal(provenLog(dir, before), 'proven');
  });
});

test("an EARLIER run's log.json does not vouch for this one", () => {
  // reports/ almost always holds a finished run already, so a check that asks
  // "is there a log.json anywhere" passes for every crash after the first.
  withFixture({ '20260731-144558': true }, (dir) => {
    const before = logFingerprints(dir);
    writeRun(dir, '20260802-114121', false);
    assert.equal(provenLog(dir, before), 'missing');
  });
});

test('a REUSED run id is proven by its new mtime, not missed for its old name', () => {
  // makeRunId is second-precise, so a directory name can repeat. Keying on
  // names alone reported a perfectly good run as unverified.
  withFixture({}, (dir) => {
    writeRun(dir, '20260802-114121', true, 1_600_000_000);
    const before = logFingerprints(dir);
    writeRun(dir, '20260802-114121', true, 1_700_000_000);
    assert.equal(provenLog(dir, before), 'proven');
  });
});

test('two reports written concurrently are ambiguous, never proof', () => {
  // Attributing one of them to us is how a crashed run reports a concurrent
  // run's findings as its own.
  withFixture({}, (dir) => {
    const before = logFingerprints(dir);
    writeRun(dir, '20260802-114121', true);
    writeRun(dir, '20260802-114122', true);
    assert.equal(provenLog(dir, before), 'ambiguous');
  });
});

test('a symlinked run directory still counts as a report', () => {
  // Dirent.isDirectory() is false for a symlink, so an entry-type check
  // silently discarded a real report. statSync follows the link.
  withFixture({}, (dir) => {
    mkdirSync(join(dir, 'reports'), { recursive: true });
    const before = logFingerprints(dir);
    const real = join(dir, 'elsewhere', '20260802-999999');
    mkdirSync(real, { recursive: true });
    writeFileSync(join(real, 'log.json'), '{"pages":[]}');
    symlinkSync(real, join(dir, 'reports', 'linked-run'));
    assert.equal(provenLog(dir, before), 'proven');
  });
});

test('no reports/ directory at all is not proven, and does not throw', () => {
  const dir = mkdtempSync(join(tmpdir(), 'ag-qa-'));
  try {
    assert.deepEqual([...logFingerprints(dir)], []);
    assert.equal(provenLog(dir, new Map()), 'missing');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('loose files beside the run directories are not mistaken for reports', () => {
  withFixture({ '20260802-114121': true }, (dir) => {
    writeFileSync(join(dir, 'reports', '20260802-114121.md'), '# report');
    assert.equal(logFingerprints(dir).size, 1);
  });
});

// ---- the policy itself, as a truth table -----------------------------------

test('an UNPROVEN clean run is not reported as clean', () => {
  // The dangerous direction. A green nobody looks behind is worse than a red,
  // and mischief can exit 0 with its report unwritten.
  assert.equal(resolveExit(0, 'missing'), 3);
  assert.equal(resolveExit(0, 'ambiguous'), 3);
});

test('a proven run keeps its own verdict, whatever it is', () => {
  assert.equal(resolveExit(0, 'proven'), 0);
  assert.equal(resolveExit(1, 'proven'), 1);
  assert.equal(resolveExit(2, 'proven'), 2);
});

test('an unproven findings run is unverified, not findings', () => {
  // The original bug: a crash exits 1 because node does, which is the same 1
  // mischief uses for HIGH findings.
  assert.equal(resolveExit(1, 'missing'), 3);
  assert.equal(resolveExit(2, 'missing'), 3);
  assert.equal(resolveExit(1, 'ambiguous'), 3);
});

test("mischief's own 3 is passed through untouched", () => {
  // It already means unverified and carries a better reason than we could.
  assert.equal(resolveExit(3, 'proven'), 3);
  assert.equal(resolveExit(3, 'missing'), 3);
});

test('replay is subject to the same rule as a fresh run', () => {
  // replay resolves the old seed/routes/steps and calls runMonkey exactly like
  // a fresh run, so it opens its own run directory and owes the same proof.
  // Exempting it let a crashed replay report findings.
  assert.equal(resolveExit(1, 'missing'), 3);
  assert.equal(resolveExit(1, 'proven'), 1);
});

test('3 is documented as unverified, not as a kind of failure', () => {
  assert.match(EXIT_MEANING[3], /UNVERIFIED/);
  assert.notEqual(EXIT_MEANING[1], EXIT_MEANING[3]);
});
