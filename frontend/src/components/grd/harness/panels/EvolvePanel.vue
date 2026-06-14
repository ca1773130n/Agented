<script setup lang="ts">
/** EvolvePanel — routes 13,14,15,16: startEvolve, listEvolveRuns, getEvolveRun, stopEvolveRun. */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../../services/api';
import type { EvolveRun } from '../../../../services/api/grdHarness';

const props = defineProps<{ projectId: string }>();
const { t } = useI18n();

const runs = ref<EvolveRun[]>([]);
const detail = ref<EvolveRun | null>(null);
const busy = ref(false);

function runId(r: EvolveRun): string {
  return String(r.id ?? r.run_id ?? '');
}

async function load() {
  try {
    const res = await grdHarnessApi.listEvolveRuns(props.projectId);
    runs.value = res.runs || [];
  } catch {
    runs.value = [];
  }
}

async function start() {
  try {
    busy.value = true;
    await grdHarnessApi.startEvolve(props.projectId);
    await load();
  } finally {
    busy.value = false;
  }
}

async function open(id: string) {
  if (!id) return;
  detail.value = await grdHarnessApi.getEvolveRun(props.projectId, id);
}

async function stop(id: string) {
  if (!id) return;
  await grdHarnessApi.stopEvolveRun(props.projectId, id);
  await load();
}

onMounted(load);
</script>

<template>
  <div class="panel">
    <p class="deprecated">{{ t('grdHarnessRounds.evolveDeprecated') }}</p>
    <div class="panel-head">
      <h4>{{ t('surface.harness.panels.evolve.title') }}</h4>
      <div class="head-actions">
        <button class="btn" @click="load">{{ t('surface.harness.panels.evolve.refresh') }}</button>
        <button class="btn" :disabled="busy" @click="start">
          {{ t('surface.harness.panels.evolve.start') }}
        </button>
      </div>
    </div>
    <ul v-if="runs.length" class="rows">
      <li v-for="r in runs" :key="runId(r)" class="row">
        <span class="rid" @click="open(runId(r))">{{ runId(r) }}</span>
        <span class="status">{{ r.status }}</span>
        <button class="btn" @click="stop(runId(r))">
          {{ t('surface.harness.panels.evolve.stop') }}
        </button>
      </li>
    </ul>
    <span v-else class="muted">{{ t('surface.harness.panels.evolve.empty') }}</span>
    <div v-if="detail" class="sub">
      <span class="lbl">{{ t('surface.harness.panels.evolve.detail') }}</span>
      <pre class="json">{{ JSON.stringify(detail, null, 2) }}</pre>
    </div>
  </div>
</template>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 0.75rem; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-head h4 { margin: 0; font-size: 0.9rem; color: var(--text-primary, #fff); }
.head-actions { display: flex; gap: 6px; }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.row { display: flex; align-items: center; gap: 8px; padding: 0.5rem; background: var(--bg-tertiary, #1a1a24); border-radius: 6px; }
.rid { color: var(--accent-cyan, #00d4ff); font-family: monospace; font-size: 0.8rem; cursor: pointer; flex: 1; }
.status { color: var(--text-tertiary, #888); font-size: 0.8rem; }
.sub { display: flex; flex-direction: column; gap: 4px; }
.lbl { color: var(--text-tertiary, #888); font-size: 0.8rem; }
.json { background: var(--bg-tertiary, #1a1a24); border-radius: 6px; padding: 0.75rem; font-size: 0.75rem; overflow: auto; max-height: 240px; color: var(--text-secondary, #aaa); }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
.deprecated { margin: 0 0 0.25rem; padding: 6px 10px; border-radius: 6px; font-size: 0.78rem;
  background: rgba(234,179,8,0.08); border: 1px solid rgba(234,179,8,0.28); color: var(--accent-amber, #eab308); }
</style>
