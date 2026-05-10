<!--
  v0.7.7: Per-super-agent activity inspector at
  /super-agents/:superAgentId/inspector. Renders a header card (rollup
  + status pill), a filter bar, and a timeline list with click-to-expand
  raw JSON payloads. Polls every 10s while mounted.

  Reuses the v0.7.0 BotHealthPage shape: same load/error/empty/grid
  surface plus the v0.7.1 trigger-events drill-down idiom for the
  timeline rows.
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { superAgentActivityApi } from '../services/api';
import type {
  SuperAgentActivityEvent,
  SuperAgentRollup,
  SuperAgentStatusPill,
} from '../services/api';

const props = defineProps<{ superAgentId: string }>();

const POLL_INTERVAL_MS = 10_000;

// Known event types surfaced by the multi-select. Mirrors the emission
// points across the backend (super_agent_session_service, streaming_helper,
// super_agents_cluster.git_action). Free-form types still work via
// payload, but the UI surfaces the canonical set explicitly.
const EVENT_TYPES = [
  'message_turn',
  'tool_call',
  'model_invoke',
  'git_action',
  'error',
] as const;

type StatusFilter = 'all' | 'ok' | 'error';
type TimeWindow = '1h' | '24h' | '7d' | '30d';

const TIME_WINDOW_TO_DAYS: Record<TimeWindow, number> = {
  '1h': 1,
  '24h': 1,
  '7d': 7,
  '30d': 30,
};

function sinceForWindow(w: TimeWindow): string {
  const now = Date.now();
  const ms =
    w === '1h'
      ? 60 * 60 * 1000
      : w === '24h'
        ? 24 * 60 * 60 * 1000
        : w === '7d'
          ? 7 * 24 * 60 * 60 * 1000
          : 30 * 24 * 60 * 60 * 1000;
  return new Date(now - ms).toISOString();
}

const rollup = ref<SuperAgentRollup | null>(null);
const events = ref<SuperAgentActivityEvent[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);
const timeWindow = ref<TimeWindow>('7d');
const selectedTypes = ref<string[]>([]);
const statusFilter = ref<StatusFilter>('all');
const expanded = ref<Set<number>>(new Set());

let pollHandle: ReturnType<typeof setInterval> | null = null;

const filteredEvents = computed<SuperAgentActivityEvent[]>(() => {
  if (statusFilter.value === 'all') return events.value;
  if (statusFilter.value === 'error')
    return events.value.filter((e) => e.status === 'error');
  return events.value.filter((e) => e.status !== 'error');
});

async function load(showSpinner: boolean = true) {
  if (showSpinner) loading.value = true;
  error.value = null;
  try {
    const since = sinceForWindow(timeWindow.value);
    const days = TIME_WINDOW_TO_DAYS[timeWindow.value];
    const [r, list] = await Promise.all([
      superAgentActivityApi.rollup(props.superAgentId, days),
      superAgentActivityApi.list(props.superAgentId, {
        limit: 200,
        since,
        types: selectedTypes.value.length ? selectedTypes.value : undefined,
      }),
    ]);
    rollup.value = r;
    events.value = list.events;
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (showSpinner) loading.value = false;
  }
}

function toggleType(t: string) {
  const idx = selectedTypes.value.indexOf(t);
  if (idx === -1) selectedTypes.value = [...selectedTypes.value, t];
  else selectedTypes.value = selectedTypes.value.filter((x) => x !== t);
}

onMounted(() => {
  load();
  pollHandle = setInterval(() => load(false), POLL_INTERVAL_MS);
});

onUnmounted(() => {
  if (pollHandle) clearInterval(pollHandle);
});

watch([timeWindow, selectedTypes, statusFilter], () => load(), { deep: true });

function toggleExpand(id: number) {
  if (expanded.value.has(id)) {
    expanded.value.delete(id);
  } else {
    expanded.value.add(id);
  }
  // re-trigger reactivity for Set
  expanded.value = new Set(expanded.value);
}

function pillLabel(s: SuperAgentStatusPill): string {
  return { active: 'Active', errored: 'Errored', idle: 'Idle', healthy: 'Healthy' }[s];
}

function fmtCost(v: number | null): string {
  if (v === null || v === undefined) return '—';
  return `$${v.toFixed(4)}`;
}

function fmtRate(v: number | null): string {
  if (v === null || v === undefined) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

function fmtPayload(p: string): string {
  try {
    return JSON.stringify(JSON.parse(p), null, 2);
  } catch {
    return p;
  }
}
</script>

<template>
  <div class="sa-inspector">
    <header class="sa-inspector__header">
      <div>
        <h1>Super-Agent Inspector</h1>
        <p class="sa-inspector__subtitle">{{ superAgentId }}</p>
      </div>
      <select
        v-model="timeWindow"
        class="sa-inspector__window"
        data-testid="window-select"
      >
        <option value="1h">Last 1 hour</option>
        <option value="24h">Last 24 hours</option>
        <option value="7d">Last 7 days</option>
        <option value="30d">Last 30 days</option>
      </select>
    </header>

    <div v-if="loading" class="sa-inspector__loading" data-testid="loading">
      Loading…
    </div>
    <div v-else-if="error" class="sa-inspector__error" data-testid="error">
      {{ error }}
      <button @click="load()">Retry</button>
    </div>
    <template v-else>
      <article
        v-if="rollup"
        class="sa-rollup"
        :data-status="rollup.status_pill"
        data-testid="rollup-card"
      >
        <header class="sa-rollup__head">
          <h2 class="sa-rollup__title">Rollup</h2>
          <span class="sa-rollup__pill" :data-status="rollup.status_pill">
            {{ pillLabel(rollup.status_pill) }}
          </span>
        </header>
        <dl class="sa-rollup__metrics">
          <div>
            <dt>Events</dt>
            <dd>{{ rollup.event_count }}</dd>
          </div>
          <div>
            <dt>Errors</dt>
            <dd>{{ rollup.error_count }}</dd>
          </div>
          <div>
            <dt>Error rate</dt>
            <dd>{{ fmtRate(rollup.error_rate) }}</dd>
          </div>
          <div>
            <dt>Total cost</dt>
            <dd>{{ fmtCost(rollup.total_cost_usd) }}</dd>
          </div>
          <div>
            <dt>Avg / event</dt>
            <dd>{{ fmtCost(rollup.cost_per_event_avg) }}</dd>
          </div>
          <div>
            <dt>Last active</dt>
            <dd>{{ rollup.last_active_at ?? '—' }}</dd>
          </div>
        </dl>
      </article>

      <div class="sa-inspector__filters">
        <fieldset class="sa-inspector__type-filter" data-testid="type-filter">
          <legend>Event types</legend>
          <label
            v-for="t in EVENT_TYPES"
            :key="t"
            class="sa-inspector__type-chip"
            :data-testid="`type-chip-${t}`"
          >
            <input
              type="checkbox"
              :value="t"
              :checked="selectedTypes.includes(t)"
              @change="toggleType(t)"
            />
            <span>{{ t }}</span>
          </label>
        </fieldset>
        <label class="sa-inspector__status-filter">
          Status
          <select v-model="statusFilter" data-testid="status-filter">
            <option value="all">All</option>
            <option value="ok">OK only</option>
            <option value="error">Errored only</option>
          </select>
        </label>
      </div>

      <div
        v-if="filteredEvents.length === 0"
        class="sa-inspector__empty"
        data-testid="empty"
      >
        No activity yet.
      </div>
      <ol v-else class="sa-timeline" data-testid="timeline">
        <li
          v-for="ev in filteredEvents"
          :key="ev.id"
          class="sa-timeline__row"
          :data-status="ev.status"
          :data-testid="`row-${ev.id}`"
        >
          <button
            class="sa-timeline__head"
            type="button"
            :data-testid="`expand-${ev.id}`"
            @click="toggleExpand(ev.id)"
          >
            <span class="sa-timeline__type">{{ ev.event_type }}</span>
            <span class="sa-timeline__ts">{{ ev.recorded_at }}</span>
            <span
              v-if="ev.cost_usd !== null"
              class="sa-timeline__cost"
            >{{ fmtCost(ev.cost_usd) }}</span>
            <span
              v-if="ev.status === 'error'"
              class="sa-timeline__err-flag"
            >ERROR</span>
          </button>
          <pre
            v-if="expanded.has(ev.id)"
            class="sa-timeline__payload"
            :data-testid="`payload-${ev.id}`"
          >{{ fmtPayload(ev.payload) }}</pre>
          <p
            v-if="expanded.has(ev.id) && ev.error_message"
            class="sa-timeline__error-msg"
          >
            {{ ev.error_message }}
          </p>
        </li>
      </ol>
    </template>
  </div>
</template>

<style scoped>
.sa-inspector { padding: 24px; max-width: 1280px; margin: 0 auto; }
.sa-inspector__header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 16px;
}
.sa-inspector__subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
  font-family: var(--font-mono, monospace);
}
.sa-rollup {
  padding: 16px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  background: var(--surface-1, rgba(255, 255, 255, 0.03));
  margin-bottom: 16px;
}
.sa-rollup__head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 12px;
}
.sa-rollup__title { font-size: 14px; font-weight: 600; margin: 0; }
.sa-rollup__pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.sa-rollup__pill[data-status='healthy'] { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
.sa-rollup__pill[data-status='active'] { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
.sa-rollup__pill[data-status='errored'] { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.sa-rollup__pill[data-status='idle'] {
  background: rgba(113, 113, 122, 0.15);
  color: #71717a;
}
.sa-rollup__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
  margin: 0;
}
.sa-rollup__metrics dt {
  font-size: 11px;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
  margin-bottom: 2px;
}
.sa-rollup__metrics dd { font-size: 16px; font-weight: 600; margin: 0; }
.sa-inspector__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-end;
  margin-bottom: 12px;
  font-size: 12px;
}
.sa-inspector__type-filter {
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 4px;
  padding: 4px 8px;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.sa-inspector__type-filter legend {
  padding: 0 4px;
  font-size: 11px;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
}
.sa-inspector__type-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  padding: 2px 4px;
}
.sa-inspector__type-chip input { margin: 0; }
.sa-inspector__status-filter {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
}
.sa-inspector__status-filter select {
  padding: 4px 8px;
  background: var(--surface-1, rgba(255, 255, 255, 0.03));
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 4px;
  color: inherit;
}
.sa-timeline {
  list-style: none;
  padding: 0;
  margin: 0;
}
.sa-timeline__row {
  border-bottom: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
}
.sa-timeline__head {
  width: 100%;
  display: grid;
  grid-template-columns: 160px 1fr auto auto;
  gap: 12px;
  padding: 8px 0;
  background: none;
  border: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  align-items: baseline;
}
.sa-timeline__head:hover {
  background: var(--surface-1, rgba(255, 255, 255, 0.03));
}
.sa-timeline__type { font-weight: 600; font-size: 13px; }
.sa-timeline__ts {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
}
.sa-timeline__cost {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
}
.sa-timeline__err-flag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}
.sa-timeline__payload {
  margin: 0;
  padding: 8px 12px;
  background: var(--surface-2, rgba(0, 0, 0, 0.25));
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-word;
}
.sa-timeline__error-msg {
  margin: 4px 0 8px;
  padding: 4px 12px;
  color: #ef4444;
  font-size: 12px;
}
.sa-inspector__loading,
.sa-inspector__error,
.sa-inspector__empty {
  padding: 24px;
  text-align: center;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
}
.sa-inspector__error { color: #ef4444; }
.sa-inspector__error button {
  margin-left: 12px;
  padding: 4px 12px;
  background: var(--surface-1, rgba(255, 255, 255, 0.03));
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 4px;
  color: inherit;
  cursor: pointer;
}
</style>
