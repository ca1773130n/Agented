<script setup lang="ts">
/** GenomePanel — routes 6,7,8,9: getGenome, snapshotGenome, listGenomeSnapshots, latestGenomeSnapshot. */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../../services/api';
import type { GenomeSnapshot } from '../../../../services/api/grdHarness';

const props = defineProps<{ projectId: string }>();
const { t } = useI18n();

const genome = ref<GenomeSnapshot | null>(null);
const latest = ref<GenomeSnapshot | null>(null);
const snapshots = ref<GenomeSnapshot[]>([]);

async function loadGenome() {
  try {
    genome.value = await grdHarnessApi.getGenome(props.projectId);
  } catch {
    genome.value = null;
  }
}

async function loadLatest() {
  try {
    latest.value = await grdHarnessApi.latestGenomeSnapshot(props.projectId);
  } catch {
    latest.value = null;
  }
}

async function loadHistory() {
  try {
    const res = await grdHarnessApi.listGenomeSnapshots(props.projectId);
    snapshots.value = res.snapshots || [];
  } catch {
    snapshots.value = [];
  }
}

async function snapshot() {
  await grdHarnessApi.snapshotGenome(props.projectId);
  await Promise.all([loadHistory(), loadLatest()]);
}

onMounted(() => {
  loadGenome();
  loadLatest();
  loadHistory();
});
</script>

<template>
  <div class="panel">
    <div class="panel-head">
      <h4>{{ t('surface.harness.panels.genome.title') }}</h4>
      <button class="btn" @click="snapshot">
        {{ t('surface.harness.panels.genome.snapshot') }}
      </button>
    </div>
    <template v-if="genome || latest || snapshots.length">
      <pre v-if="genome" class="json">{{ JSON.stringify(genome, null, 2) }}</pre>
      <div class="sub">
        <span class="lbl">{{ t('surface.harness.panels.genome.latest') }}</span>
        <pre v-if="latest" class="json">{{ JSON.stringify(latest, null, 2) }}</pre>
      </div>
      <div class="sub">
        <span class="lbl"
          >{{ t('surface.harness.panels.genome.history') }} ({{ snapshots.length }})</span
        >
      </div>
    </template>
    <span v-else class="muted">{{ t('surface.harness.panels.genome.empty') }}</span>
  </div>
</template>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 0.75rem; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-head h4 { margin: 0; font-size: 0.9rem; color: var(--text-primary, #fff); }
.sub { display: flex; flex-direction: column; gap: 4px; }
.lbl { color: var(--text-tertiary, #888); font-size: 0.8rem; }
.json { background: var(--bg-tertiary, #1a1a24); border-radius: 6px; padding: 0.75rem; font-size: 0.75rem; overflow: auto; max-height: 240px; color: var(--text-secondary, #aaa); }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
