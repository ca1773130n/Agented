<!--
  HarnessLayersCard — operator's read+toggle surface for a bot's harness IR.

  Picks a bot, lists its enabled layers grouped by H2/H3/H4/H5 with an
  expandable payload preview and a per-row enabled toggle. Below the
  layers, shows recent execution snapshots with which layer versions
  were active, closing the loop from "what's configured" to "what ran".
-->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { triggerApi } from '../../../services/api';
import type { Trigger } from '../../../services/api/types/triggers';
import {
  harnessLayersApi,
  type HarnessLayersByKind,
  type HarnessLayerRow,
  type RunHistorySnapshot,
} from '../../../services/api/harness-layers';
import LoadingState from '../../../components/base/LoadingState.vue';
import ErrorState from '../../../components/base/ErrorState.vue';

const emit = defineEmits<{ loaded: [slug: string] }>();

const bots = ref<Trigger[]>([]);
const selectedBotId = ref<string>('');
const layers = ref<HarnessLayersByKind | null>(null);
const snapshots = ref<RunHistorySnapshot[]>([]);
const isLoading = ref(false);
const loadError = ref<string | null>(null);
const expanded = ref<Set<string>>(new Set());
const togglingId = ref<string | null>(null);

const KINDS = ['h2', 'h3', 'h4', 'h5'] as const;
const KIND_LABEL: Record<typeof KINDS[number], string> = {
  h2: 'Action realization',
  h3: 'Environment contract',
  h4: 'Trajectory regulation',
  h5: 'Procedural skills',
};

const totalEnabled = computed(() => {
  if (!layers.value) return 0;
  return KINDS.reduce((sum, k) => sum + layers.value![k].length, 0);
});

async function loadBots() {
  try {
    const res = await triggerApi.list();
    bots.value = res?.triggers || [];
    if (!selectedBotId.value && bots.value.length > 0) {
      selectedBotId.value = bots.value[0].id;
    }
  } catch {
    bots.value = [];
  }
}

async function loadForBot() {
  if (!selectedBotId.value) {
    layers.value = null;
    snapshots.value = [];
    return;
  }
  isLoading.value = true;
  loadError.value = null;
  try {
    const [layersRes, historyRes] = await Promise.all([
      harnessLayersApi.listForBot(selectedBotId.value),
      harnessLayersApi.runHistory(selectedBotId.value, 10),
    ]);
    layers.value = layersRes.layers;
    snapshots.value = historyRes.snapshots;
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : 'Failed to load';
    layers.value = null;
  } finally {
    isLoading.value = false;
    emit('loaded', 'harness-layers-card');
  }
}

async function toggle(row: HarnessLayerRow) {
  if (togglingId.value) return;
  togglingId.value = row.id;
  try {
    await harnessLayersApi.toggle(row.id, !row.enabled);
    await loadForBot();
  } finally {
    togglingId.value = null;
  }
}

function toggleExpand(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id);
  else expanded.value.add(id);
}

function fmtVersions(v: Record<string, number>): string {
  const entries = Object.entries(v);
  if (entries.length === 0) return '—';
  return entries
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, n]) => `${k.toUpperCase()}@v${n}`)
    .join(' ');
}

onMounted(async () => {
  await loadBots();
  await loadForBot();
});
</script>

<template>
  <section
    id="harness-layers-card"
    class="lane-card"
    data-testid="harness-layers-card"
  >
    <header class="lane-card__head">
      <div>
        <h2 class="lane-card__title">Harness layers</h2>
        <p class="lane-card__subtitle">
          Active four-layer IR for the selected bot + recent execution snapshots.
        </p>
      </div>
      <select
        v-model="selectedBotId"
        class="bot-select"
        data-testid="layers-bot-select"
        @change="loadForBot"
      >
        <option v-if="bots.length === 0" value="" disabled>
          No bots available
        </option>
        <option v-for="b in bots" :key="b.id" :value="b.id">
          {{ b.name }} ({{ b.id }})
        </option>
      </select>
    </header>

    <LoadingState v-if="isLoading" message="Loading…" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="loadForBot" />
    <template v-else-if="layers">
      <p v-if="totalEnabled === 0" class="empty" data-testid="layers-empty">
        No enabled layers for this bot.
      </p>
      <div v-else class="kinds">
        <section
          v-for="kind in KINDS"
          :key="kind"
          class="kind"
          :data-testid="`layers-kind-${kind}`"
        >
          <h3 class="kind__head">
            <span class="kind__label">{{ kind.toUpperCase() }}</span>
            <span class="kind__name">{{ KIND_LABEL[kind] }}</span>
            <span class="kind__count">{{ layers[kind].length }}</span>
          </h3>
          <ul class="rows">
            <li
              v-for="r in layers[kind]"
              :key="r.id"
              class="row"
              :data-testid="`layer-row-${r.id}`"
            >
              <header class="row__head">
                <button
                  class="row__expand"
                  :data-testid="`layer-expand-${r.id}`"
                  @click="toggleExpand(r.id)"
                >{{ expanded.has(r.id) ? '▾' : '▸' }}</button>
                <span class="row__name">{{ r.name }}</span>
                <code class="row__version">v{{ r.version }}</code>
                <span class="row__source" :data-kind="r.source_kind">
                  {{ r.source_kind }}
                </span>
                <button
                  class="row__toggle"
                  :class="{ enabled: r.enabled }"
                  :disabled="togglingId === r.id"
                  :data-testid="`layer-toggle-${r.id}`"
                  @click="toggle(r)"
                >{{ r.enabled ? 'enabled' : 'disabled' }}</button>
              </header>
              <pre
                v-if="expanded.has(r.id)"
                class="row__payload"
                :data-testid="`layer-payload-${r.id}`"
              >{{ JSON.stringify(r.payload, null, 2) }}</pre>
            </li>
          </ul>
        </section>
      </div>

      <section class="history" data-testid="layers-run-history">
        <h3 class="history__title">Recent runs ({{ snapshots.length }})</h3>
        <p v-if="snapshots.length === 0" class="muted">
          No executions snapshotted yet.
        </p>
        <ul v-else class="history-list">
          <li
            v-for="s in snapshots"
            :key="s.execution_id"
            class="history-row"
            :data-testid="`history-row-${s.execution_id}`"
          >
            <code class="history-id">{{ s.execution_id }}</code>
            <span
              class="history-applied"
              :class="{ applied: s.applied }"
            >{{ s.applied ? 'applied' : 'snapshot-only' }}</span>
            <span class="history-versions">{{ fmtVersions(s.layer_versions) }}</span>
            <span class="history-when">{{ s.created_at }}</span>
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>

<style scoped>
.lane-card {
  padding: 20px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 10px;
  background: var(--bg-secondary, rgba(255, 255, 255, 0.02));
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.lane-card__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.lane-card__title { font-size: 14px; font-weight: 600; margin: 0; color: var(--text-primary); }
.lane-card__subtitle { font-size: 12px; margin: 4px 0 0; color: var(--text-tertiary); }

.bot-select {
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
  color: var(--text-primary);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.12));
  border-radius: 4px;
  padding: 6px 8px;
  font-size: 12px;
  min-width: 220px;
}

.kinds { display: flex; flex-direction: column; gap: 12px; }
.kind { display: flex; flex-direction: column; gap: 6px; }
.kind__head {
  display: flex; align-items: baseline; gap: 8px;
  font-size: 11px;
  color: var(--text-tertiary);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.kind__label { font-weight: 700; color: var(--text-secondary); }
.kind__name { flex: 1; }
.kind__count { font-variant-numeric: tabular-nums; }

.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.row {
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 6px;
  padding: 6px 10px;
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
}
.row__head { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.row__expand {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 12px;
  cursor: pointer;
}
.row__name { color: var(--text-primary); flex: 1; }
.row__version { font-family: var(--font-mono, monospace); font-size: 11px; color: var(--text-tertiary); }
.row__source {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  letter-spacing: 0.04em;
  background: var(--text-tertiary, #6b7280);
  color: white;
}
.row__source[data-kind='manual']   { background: var(--accent-cyan,  #06b6d4); }
.row__source[data-kind='evolved']  { background: var(--accent-amber, #f59e0b); }
.row__source[data-kind='template'] { background: var(--text-tertiary, #6b7280); }

.row__toggle {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 3px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.12));
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.row__toggle.enabled { border-color: var(--accent-green, #10b981); color: var(--accent-green, #10b981); }
.row__toggle:disabled { opacity: 0.5; cursor: not-allowed; }
.row__payload {
  background: var(--bg-primary, rgba(0, 0, 0, 0.2));
  padding: 8px;
  margin: 6px 0 0;
  border-radius: 4px;
  font-size: 11px;
  max-height: 180px;
  overflow-y: auto;
  white-space: pre-wrap;
}

.history { display: flex; flex-direction: column; gap: 6px; padding-top: 10px; border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06)); }
.history__title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin: 0;
}
.history-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.history-row { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--text-secondary); }
.history-id { font-family: var(--font-mono, monospace); }
.history-applied {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--text-tertiary, #6b7280);
  color: white;
  letter-spacing: 0.04em;
}
.history-applied.applied { background: var(--accent-green, #10b981); }
.history-versions { font-family: var(--font-mono, monospace); flex: 1; }
.history-when { color: var(--text-tertiary); }

.empty { font-size: 12px; color: var(--text-tertiary); margin: 0; }
.muted { font-size: 11px; color: var(--text-tertiary); margin: 0; }
</style>
