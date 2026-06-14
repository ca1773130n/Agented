<script setup lang="ts">
/** HarnessRoundsPanel — GRD 0.4.x life-harness rounds (supersedes EvolvePanel).
 *  Triggers `gd harness round` (background) and lists mirrored rounds. */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../../services/api';
import type { LifeHarnessRound } from '../../../../services/api/grdHarness';

const props = defineProps<{ projectId: string }>();
const { t } = useI18n();

const rounds = ref<LifeHarnessRound[]>([]);
const busy = ref(false);
const auto = ref(false);
const error = ref('');

async function load() {
  try {
    const res = await grdHarnessApi.listHarnessRounds(props.projectId);
    rounds.value = res.rounds || [];
  } catch {
    rounds.value = [];
  }
}

async function run() {
  error.value = '';
  busy.value = true;
  try {
    await grdHarnessApi.runHarnessRound(props.projectId, { auto: auto.value });
    // The round runs in the background; poll shortly after for the result.
    setTimeout(load, 1500);
  } catch {
    error.value = t('grdHarnessRounds.gdMissing');
  } finally {
    busy.value = false;
  }
}

async function revert(roundId: string) {
  if (!roundId) return;
  await grdHarnessApi.revertHarnessRound(props.projectId, roundId);
  await load();
}

function pct(c: unknown): string {
  return typeof c === 'number' ? `${Math.round(c * 100)}%` : '';
}

onMounted(load);
</script>

<template>
  <div class="panel">
    <div class="panel-head">
      <h4>{{ t('grdHarnessRounds.title') }}</h4>
      <div class="head-actions">
        <label class="auto"><input type="checkbox" v-model="auto" /> {{ t('grdHarnessRounds.auto') }}</label>
        <button class="btn" @click="load">{{ t('grdHarnessRounds.colStatus') }}</button>
        <button class="btn" data-testid="run-round" :disabled="busy" @click="run">
          {{ busy ? t('grdHarnessRounds.running') : t('grdHarnessRounds.runRound') }}
        </button>
      </div>
    </div>
    <p class="muted desc">{{ t('grdHarnessRounds.description') }}</p>
    <p v-if="error" class="error">{{ error }}</p>
    <ul v-if="rounds.length" class="rows">
      <li v-for="r in rounds" :key="r.round_id" class="row">
        <span class="rid">{{ r.round_id }}</span>
        <span class="status">{{ r.status }}</span>
        <span v-if="r.summary" class="summary">{{ r.summary }}</span>
        <span v-if="r.confidence != null" class="conf">{{ pct(r.confidence) }}</span>
        <button
          v-if="r.applied_sha"
          class="btn"
          :data-testid="`revert-${r.round_id}`"
          @click="revert(r.round_id)"
        >
          {{ t('grdHarnessRounds.revert') }}
        </button>
      </li>
    </ul>
    <span v-else class="muted">{{ t('grdHarnessRounds.noRounds') }}</span>
  </div>
</template>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 0.75rem; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-head h4 { margin: 0; font-size: 0.9rem; color: var(--text-primary, #fff); }
.head-actions { display: flex; gap: 6px; align-items: center; }
.auto { display: inline-flex; align-items: center; gap: 4px; font-size: 0.8rem; color: var(--text-tertiary, #888); }
.desc { margin: 0; }
.error { color: var(--accent-red, #ef4444); font-size: 0.8rem; margin: 0; }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.row { display: flex; align-items: center; gap: 8px; padding: 0.5rem; background: var(--bg-tertiary, #1a1a24); border-radius: 6px; }
.rid { color: var(--accent-cyan, #00d4ff); font-family: monospace; font-size: 0.8rem; }
.status { color: var(--text-tertiary, #888); font-size: 0.8rem; }
.summary { flex: 1; color: var(--text-secondary, #aaa); font-size: 0.8rem; }
.conf { color: var(--text-tertiary, #888); font-size: 0.8rem; font-variant-numeric: tabular-nums; }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
