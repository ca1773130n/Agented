/**
 * useMemoryJob — run a memory/observability query as a BACKGROUND job the
 * operator can navigate away from, and read it back later from history.
 *
 * `run(params?)` dispatches the job and polls until it settles; `showLatest()`
 * loads the newest job of this kind INSTANTLY if it is already complete, or
 * resumes polling if one is still running (read-later semantics). The poll
 * timer is always cleared on unmount and after the job settles — no leaks, and
 * no state writes after unmount (an in-flight await is guarded by `alive`).
 *
 * The result is the SAME kind-specific payload the old sync endpoints returned
 * (doctor → DoctorResult, sessions → SessionsResult, …); callers cast via <T>.
 */
import { ref, onUnmounted, type Ref } from 'vue';
import { memorySystemApi } from '../services/api/memory-system';
import type { MemoryQueryKind } from '../services/api/memory-system';

export type MemoryJobStatus = 'idle' | 'running' | 'completed' | 'failed';

export interface UseMemoryJob<T> {
  status: Ref<MemoryJobStatus>;
  result: Ref<T | null>;
  error: Ref<string | null>;
  jobId: Ref<string | null>;
  running: Ref<boolean>;
  run: (params?: Record<string, unknown> | null) => Promise<void>;
  showLatest: () => Promise<void>;
  stop: () => void;
}

const POLL_MS = 1200;

export function useMemoryJob<T = unknown>(kind: MemoryQueryKind): UseMemoryJob<T> {
  const status = ref<MemoryJobStatus>('idle');
  const result = ref<T | null>(null) as Ref<T | null>;
  const error = ref<string | null>(null);
  const jobId = ref<string | null>(null);
  const running = ref(false);

  let timer: ReturnType<typeof setInterval> | null = null;
  let alive = true;

  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  // Extract a human-ish error string from a settled job payload.
  function reasonOf(payload: unknown): string | null {
    if (payload && typeof payload === 'object' && 'reason' in payload) {
      const r = (payload as { reason?: unknown }).reason;
      if (typeof r === 'string' && r) return r;
    }
    return null;
  }

  function settle(jobStatus: 'completed' | 'failed', payload: unknown) {
    stop();
    running.value = false;
    status.value = jobStatus;
    if (jobStatus === 'completed') {
      result.value = (payload ?? null) as T | null;
    } else {
      error.value = reasonOf(payload) || 'failed';
    }
  }

  function poll(id: string) {
    stop();
    timer = setInterval(async () => {
      let job;
      try {
        job = await memorySystemApi.getMemoryJob(id);
      } catch (e) {
        if (!alive) { stop(); return; }
        stop();
        running.value = false;
        status.value = 'failed';
        error.value = (e as Error).message || 'failed';
        return;
      }
      if (!alive) { stop(); return; }
      if (job.status === 'running') return;
      settle(job.status === 'completed' ? 'completed' : 'failed', job.result);
    }, POLL_MS);
  }

  async function run(params?: Record<string, unknown> | null) {
    if (running.value) return;
    stop();
    running.value = true;
    status.value = 'running';
    error.value = null;
    try {
      const res = await memorySystemApi.runMemoryQuery(kind, params ?? null);
      if (!alive) { stop(); return; }
      jobId.value = res.job_id;
      poll(res.job_id);
    } catch (e) {
      running.value = false;
      status.value = 'failed';
      error.value = (e as Error).message || 'failed';
    }
  }

  // Instant last result (read-later); resume polling if the newest job is running.
  async function showLatest() {
    try {
      const { jobs } = await memorySystemApi.listMemoryJobs(kind, 1);
      if (!alive) return;
      const latest = jobs?.[0];
      if (!latest) return;
      jobId.value = latest.job_id;
      if (latest.status === 'running') {
        running.value = true;
        status.value = 'running';
        poll(latest.job_id);
        return;
      }
      const job = await memorySystemApi.getMemoryJob(latest.job_id);
      if (!alive) return;
      settle(job.status === 'completed' ? 'completed' : 'failed', job.result);
    } catch {
      // Soft-fail: leave the surface idle so the operator can Run manually.
    }
  }

  onUnmounted(() => { alive = false; stop(); });

  return { status, result, error, jobId, running, run, showLatest, stop };
}
