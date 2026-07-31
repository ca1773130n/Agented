/**
 * `--wait` — block until an async op finishes.
 *
 * Several operations (compile, ingest, distill, build-site) return a `job_id` and
 * expect you to poll. That is an API detail leaking into the CLI: a person
 * running `ag mem compile` wants the compile, not a receipt they have to redeem.
 *
 * So `--wait` polls to a terminal status and makes the JOB's outcome the command's
 * outcome — a failed job exits non-zero, rather than exiting 0 because the
 * dispatch succeeded. That distinction is the whole reason this file exists.
 */

import { request } from './transport.ts';
import type { Resolved } from './config.ts';
import { note, isTTY } from './output.ts';

const JOB_PATH = '/admin/system/memory/tesserae/jobs';
const TERMINAL = new Set(['completed', 'failed']);

export interface JobOutcome {
  status: string;
  job: Record<string, unknown>;
  /** 0 when the job itself succeeded. */
  code: number;
}

export async function waitForJob(
  jobId: string,
  profile: Resolved,
  opts: { timeoutMs?: number; intervalMs?: number; label?: string } = {},
): Promise<JobOutcome> {
  const timeoutMs = opts.timeoutMs ?? 30 * 60_000;
  const intervalMs = opts.intervalMs ?? 2000;
  const started = Date.now();
  let spun = 0;
  let consecutiveErrors = 0;

  for (;;) {
    // A long op can make the single-worker backend briefly unreachable, and one
    // dropped poll must not abandon a job that is running fine. MEASURED: two
    // real compiles both COMPLETED while `--wait` reported "cannot reach" and
    // exited 4 — the run was healthy, the watcher was not. Tolerate a short
    // outage; give up only if it persists.
    let res;
    try {
      res = await request({ method: 'GET', path: `${JOB_PATH}/${encodeURIComponent(jobId)}`, profile });
      consecutiveErrors = 0;
    } catch (e) {
      if (++consecutiveErrors > 15) {
        note(`lost contact with the server for ${consecutiveErrors} polls — the job may still be running: ${jobId}`);
        return { status: 'unknown', job: {}, code: 4 };
      }
      await new Promise((r) => setTimeout(r, intervalMs));
      continue;
    }
    if (res.status === 404) {
      // The job map is in-process; a server restart loses it. Say so plainly
      // rather than reporting a failure the job may not have had.
      note(`job ${jobId} is unknown to the server (restarted?) — outcome unknown`);
      return { status: 'unknown', job: {}, code: 4 };
    }
    if (res.status >= 400) {
      note(`could not poll job ${jobId}: HTTP ${res.status}`);
      return { status: 'unknown', job: {}, code: 7 };
    }

    const job = (res.body ?? {}) as Record<string, unknown>;
    const status = String(job.status ?? 'running');

    if (TERMINAL.has(status)) {
      if (isTTY && spun) process.stderr.write('\n');
      const result = job.result as Record<string, unknown> | undefined;
      const reason = result?.reason ?? job.error;
      if (status === 'failed') {
        note(`job failed${reason ? `: ${reason}` : ''}`);
        return { status, job, code: 8 };
      }
      // `completed` still carries an ok:false result on a refusal (e.g. a distill
      // that was priced over budget). Dispatching fine is not succeeding.
      if (result && result.ok === false) {
        note(`job completed but the operation did not succeed: ${reason ?? '(no reason given)'}`);
        return { status, job, code: 8 };
      }
      return { status, job, code: 0 };
    }

    if (Date.now() - started > timeoutMs) {
      note(`still ${status} after ${Math.round(timeoutMs / 1000)}s — giving up on waiting (the job keeps running)`);
      return { status, job, code: 5 };
    }

    if (isTTY) {
      const secs = Math.round((Date.now() - started) / 1000);
      process.stderr.write(`\r${opts.label ?? 'working'}… ${secs}s`);
      spun++;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

/** Pull a job id out of whatever the dispatch endpoint returned. */
export function jobIdOf(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  const o = body as Record<string, unknown>;
  const id = o.job_id ?? o.jobId;
  return typeof id === 'string' && id ? id : null;
}
