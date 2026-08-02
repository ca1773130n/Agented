/**
 * Unit tests for `ag qa`'s crash detection.
 *
 * The command's contract is that exit 3 means "the report is not evidence of
 * anything". The first live run against the app broke it: mischief threw on
 * route 1 of 24, node exited 1 for the uncaught exception, and `ag qa` printed
 * "exit 1 — HIGH findings" for a run that had tested nothing.
 *
 * The distinguishing fact is on disk, not in the exit code: a finished run
 * writes reports/<runId>/log.json, a crashed one leaves the directory with only
 * shots/. These cover that, including the case where the only log.json present
 * belongs to an earlier run.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { EXIT_MEANING, runDirs, wroteLog } from '../commands/qa.ts';

/** Build a fake frontend/ dir; `runs` maps a run id to whether it finished. */
function fixture(runs: Record<string, boolean>): string {
  const dir = mkdtempSync(join(tmpdir(), 'ag-qa-'));
  for (const [id, finished] of Object.entries(runs)) {
    const run = join(dir, 'reports', id);
    mkdirSync(join(run, 'shots'), { recursive: true });
    if (finished) writeFileSync(join(run, 'log.json'), '{"pages":[]}');
  }
  return dir;
}

test('a crashed run — new directory, no log.json — is not verified', () => {
  const dir = fixture({ '20260802-114121': false });
  try {
    assert.equal(wroteLog(dir, []), false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('a finished run — new directory with log.json — is verified', () => {
  const dir = fixture({ '20260802-114121': true });
  try {
    assert.equal(wroteLog(dir, []), true);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('an EARLIER run\'s log.json does not vouch for this one', () => {
  // The subtle failure: reports/ almost always holds a finished run already, so
  // a check that merely asks "is there a log.json anywhere" passes for every
  // crash after the first one.
  const dir = fixture({ '20260731-144558': true, '20260802-114121': false });
  try {
    assert.equal(wroteLog(dir, ['20260731-144558']), false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('no reports/ directory at all is not verified, and does not throw', () => {
  const dir = mkdtempSync(join(tmpdir(), 'ag-qa-'));
  try {
    assert.deepEqual(runDirs(dir), []);
    assert.equal(wroteLog(dir, []), false);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('runDirs ignores loose files next to the run directories', () => {
  const dir = fixture({ '20260802-114121': true });
  writeFileSync(join(dir, 'reports', '20260802-114121.md'), '# report');
  try {
    assert.deepEqual(runDirs(dir), ['20260802-114121']);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('3 is documented as unverified, not as a kind of failure', () => {
  assert.match(EXIT_MEANING[3], /UNVERIFIED/);
  assert.notEqual(EXIT_MEANING[1], EXIT_MEANING[3]);
});
