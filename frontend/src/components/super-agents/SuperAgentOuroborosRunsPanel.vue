<script setup lang="ts">
/**
 * SuperAgentOuroborosRunsPanel — v0.7.95.
 *
 * Inspector-side counterpart to the operator-side
 * ``SuperAgentOuroborosDialog`` (v0.7.92): the dialog kicks runs off,
 * this panel surfaces them after the fact.
 *
 * Reads ``GET /admin/super-agents/{id}/ouroboros-runs`` (added in
 * v0.7.92 via the ``project_sessions.super_agent_id`` linkage) and
 * shows one row per spawned goal_loop session with status,
 * iteration count, and timing. Each row links into the project's
 * session view (existing ``project-management`` route, sessions tab
 * focused on the session id), so the operator can drop into a live
 * Ouroboros run without leaving the SA flow.
 *
 * Self-fetching on mount, polls on a 7s cadence while the page is
 * open so an active run's iteration_count + last_activity update
 * without a manual refresh.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { superAgentApi } from '../../services/api';
import { safeFormatRelative } from '../../utils/datetime';

const props = defineProps<{
  superAgentId: string;
  /** Max runs to show. Defaults to the API default (20). */
  limit?: number;
}>();

const router = useRouter();

interface OuroborosRun {
  session_id: string;
  project_id: string;
  status: string;
  execution_type: string;
  started_at: string | null;
  ended_at: string | null;
  last_activity_at: string | null;
  iteration_count: number;
}

const runs = ref<OuroborosRun[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

// Poll while any run is still active so iteration_count animates.
const POLL_MS = 7_000;
let pollHandle: ReturnType<typeof setInterval> | null = null;

const hasActiveRun = computed(() =>
  runs.value.some(r => r.status === 'active' || r.status === 'running'),
);

async function load(showSpinner = true) {
  if (showSpinner) loading.value = true;
  error.value = null;
  // Capture the SA id at call-start so a slow in-flight request
  // from a previously-mounted SA can't overwrite ``runs.value``
  // after the prop changes — that would mis-render the new SA's
  // panel and also re-toggle ``hasActiveRun`` from stale data,
  // restarting polling on the wrong account.
  const requestedFor = props.superAgentId;
  try {
    const res = await superAgentApi.listOuroborosRuns(
      requestedFor,
      props.limit,
    );
    if (requestedFor !== props.superAgentId) return;
    // Skip the reassignment when the poll returned the same set
    // we already have. Otherwise the 7s poll re-renders all rows
    // (and re-runs ``formatRelative`` per row) on every cycle even
    // when nothing actually changed.
    if (!runsChanged(runs.value, res.runs)) return;
    runs.value = res.runs;
  } catch (e: unknown) {
    if (requestedFor !== props.superAgentId) return;
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (showSpinner && requestedFor === props.superAgentId) {
      loading.value = false;
    }
  }
}

function ensurePolling() {
  // Only poll when an active run could change. When nothing's
  // running the panel is effectively a static history list, so
  // the 7s poll is wasted work + log spam.
  if (hasActiveRun.value && !pollHandle) {
    pollHandle = setInterval(() => load(false), POLL_MS);
  } else if (!hasActiveRun.value && pollHandle) {
    clearInterval(pollHandle);
    pollHandle = null;
  }
}

watch(hasActiveRun, ensurePolling);
watch(
  () => props.superAgentId,
  () => {
    // Clear stale rows so the panel doesn't briefly show the
    // previous SA's runs while the new fetch is in flight.
    runs.value = [];
    load();
  },
);

onMounted(async () => {
  await load();
  ensurePolling();
});

onUnmounted(() => {
  if (pollHandle) clearInterval(pollHandle);
});

function statusClass(status: string): string {
  if (status === 'active' || status === 'running') return 'status--active';
  if (status === 'completed') return 'status--completed';
  if (status === 'error' || status === 'failed') return 'status--error';
  if (status === 'cancelled' || status === 'paused') return 'status--neutral';
  return 'status--neutral';
}

function formatRelative(iso: string | null): string {
  return safeFormatRelative(iso, '—');
}

function runsChanged(prev: OuroborosRun[], next: OuroborosRun[]): boolean {
  if (prev.length !== next.length) return true;
  for (let i = 0; i < prev.length; i++) {
    const a = prev[i];
    const b = next[i];
    if (
      a.session_id !== b.session_id ||
      a.status !== b.status ||
      a.iteration_count !== b.iteration_count ||
      a.last_activity_at !== b.last_activity_at ||
      a.ended_at !== b.ended_at
    ) {
      return true;
    }
  }
  return false;
}

function openRun(run: OuroborosRun) {
  // The project-management page's Sessions tab renders the goal_loop
  // session as a chat-style panel keyed by session id. Use a query
  // param so the panel auto-selects.
  router.push({
    name: 'project-management',
    params: { projectId: run.project_id },
    query: { sessionId: run.session_id, tab: 'sessions' },
  });
}
</script>

<template>
  <article class="ouroboros-panel" data-testid="ouroboros-runs-panel">
    <header class="ouroboros-panel__head">
      <h2 class="ouroboros-panel__title">Recent Ouroboros runs</h2>
      <button
        v-if="!loading"
        type="button"
        class="ouroboros-panel__refresh"
        data-testid="ouroboros-runs-refresh"
        :aria-label="`Refresh Ouroboros runs for super-agent ${superAgentId}`"
        @click="load()"
      >
        Refresh
      </button>
    </header>

    <div v-if="loading" class="ouroboros-panel__empty">Loading…</div>
    <div
      v-else-if="error"
      class="ouroboros-panel__error"
      data-testid="ouroboros-runs-error"
    >
      {{ error }}
    </div>
    <div
      v-else-if="runs.length === 0"
      class="ouroboros-panel__empty"
      data-testid="ouroboros-runs-empty"
    >
      No Ouroboros runs yet. Use the
      <strong>Run Ouroboros</strong> button on the SA list page to
      spawn one — it'll appear here.
    </div>
    <ol v-else class="ouroboros-panel__list" data-testid="ouroboros-runs-list">
      <li
        v-for="r in runs"
        :key="r.session_id"
        class="ouroboros-row"
        :data-testid="`ouroboros-row-${r.session_id}`"
      >
        <button
          type="button"
          class="ouroboros-row__btn"
          :aria-label="`Open Ouroboros session ${r.session_id}`"
          @click="openRun(r)"
        >
          <div class="ouroboros-row__head">
            <span class="ouroboros-row__id">{{ r.session_id }}</span>
            <span
              class="ouroboros-row__status"
              :class="statusClass(r.status)"
              :data-status="r.status"
            >
              {{ r.status }}
            </span>
          </div>
          <div class="ouroboros-row__meta">
            <span class="meta-item">
              <span class="meta-label">iterations</span>
              <span class="meta-value">{{ r.iteration_count }}</span>
            </span>
            <span class="meta-item">
              <span class="meta-label">started</span>
              <span class="meta-value" :title="r.started_at ?? ''">
                {{ formatRelative(r.started_at) }}
              </span>
            </span>
            <span v-if="r.ended_at" class="meta-item">
              <span class="meta-label">ended</span>
              <span class="meta-value" :title="r.ended_at">
                {{ formatRelative(r.ended_at) }}
              </span>
            </span>
            <span v-else class="meta-item">
              <span class="meta-label">last activity</span>
              <span class="meta-value" :title="r.last_activity_at ?? ''">
                {{ formatRelative(r.last_activity_at) }}
              </span>
            </span>
            <span class="meta-item meta-item--project">
              <span class="meta-label">project</span>
              <span class="meta-value">{{ r.project_id }}</span>
            </span>
          </div>
        </button>
      </li>
    </ol>
  </article>
</template>

<style scoped>
.ouroboros-panel {
  background: var(--bg-secondary, #1a1a20);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.ouroboros-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.ouroboros-panel__title {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
}
.ouroboros-panel__refresh {
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
}
.ouroboros-panel__refresh:hover {
  background: var(--bg-primary);
  color: var(--text-primary);
}
.ouroboros-panel__empty {
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.5;
  padding: 8px 4px;
}
.ouroboros-panel__error {
  color: var(--accent-red, #ff5470);
  font-size: 12px;
  padding: 8px 4px;
}
.ouroboros-panel__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ouroboros-row__btn {
  width: 100%;
  text-align: left;
  background: var(--bg-primary, #101015);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  padding: 8px 10px;
  cursor: pointer;
  color: inherit;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ouroboros-row__btn:hover {
  border-color: var(--accent-violet, #8855ff);
}
.ouroboros-row__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.ouroboros-row__id {
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, monospace);
  font-size: 12px;
  color: var(--text-primary);
}
.ouroboros-row__status {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid var(--border-default);
}
.status--active {
  background: rgba(80, 200, 120, 0.12);
  color: #5ce18a;
  border-color: rgba(80, 200, 120, 0.4);
}
.status--completed {
  background: rgba(80, 120, 200, 0.12);
  color: #7aa6ff;
  border-color: rgba(80, 120, 200, 0.4);
}
.status--error {
  background: rgba(255, 84, 112, 0.12);
  color: #ff5470;
  border-color: rgba(255, 84, 112, 0.4);
}
.status--neutral {
  color: var(--text-tertiary);
}
.ouroboros-row__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 11px;
  color: var(--text-tertiary);
}
.meta-item {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
}
.meta-label {
  color: var(--text-tertiary);
}
.meta-value {
  color: var(--text-secondary);
}
.meta-item--project .meta-value {
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, monospace);
}
</style>
