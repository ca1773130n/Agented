<script setup lang="ts">
/** GenomePanel — routes 6,7,8,9: getGenome, snapshotGenome, listGenomeSnapshots, latestGenomeSnapshot. */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi, ApiError } from '../../../../services/api';
import type {
  GenomeSnapshot,
  PatternSuggestion,
} from '../../../../services/api/grdHarness';

const props = defineProps<{ projectId: string }>();
const { t } = useI18n();

const genome = ref<GenomeSnapshot | null>(null);
const latest = ref<GenomeSnapshot | null>(null);
const snapshots = ref<GenomeSnapshot[]>([]);

// ─── Pattern mining (gd patterns → GENOME-SUGGESTIONS) ───
const suggestions = ref<PatternSuggestion[]>([]);
const suggestionsSaved = ref(false); // true once GENOME-SUGGESTIONS.md written (apply)
const baseline = ref<number | null>(null);
const reflectionsScanned = ref<number | null>(null);
const mining = ref(false);
const patternsError = ref('');
const promotedSlug = ref('');

async function loadSuggestions() {
  try {
    const res = await grdHarnessApi.getGenomeSuggestions(props.projectId);
    suggestions.value = res.suggestions || [];
    suggestionsSaved.value = res.applied;
    baseline.value = res.baseline_confirmed_rate;
    reflectionsScanned.value = res.reflections_scanned;
  } catch {
    /* no prior run */
  }
}

async function mine(apply: boolean) {
  patternsError.value = '';
  mining.value = true;
  try {
    const res = await grdHarnessApi.minePatterns(props.projectId, { apply });
    suggestions.value = res.data?.suggestions || [];
    baseline.value = res.data?.baseline_confirmed_rate ?? null;
    reflectionsScanned.value = res.data?.reflections_scanned ?? null;
    if (apply) suggestionsSaved.value = !!res.data?.applied;
  } catch (e) {
    patternsError.value = e instanceof ApiError ? e.message : t('surface.harness.panels.genome.patterns.failed');
  } finally {
    mining.value = false;
  }
}

async function promote(s: PatternSuggestion) {
  patternsError.value = '';
  try {
    await grdHarnessApi.promoteSuggestion(props.projectId, `${s.token}-rate`);
    promotedSlug.value = `${s.token}-rate`;
    await loadGenome();
  } catch (e) {
    patternsError.value = e instanceof ApiError ? e.message : t('surface.harness.panels.genome.patterns.failed');
  }
}

function pctOf(n: number | null | undefined): string {
  return typeof n === 'number' ? `${Math.round(n * 100)}%` : '—';
}

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
  loadSuggestions();
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

    <!-- GRD 0.4.1 pattern mining → GENOME-SUGGESTIONS → promote -->
    <div class="patterns">
      <div class="patterns-head">
        <span class="lbl">{{ t('surface.harness.panels.genome.patterns.title') }}</span>
        <div class="patterns-actions">
          <button class="btn" data-testid="patterns-mine" :disabled="mining" @click="mine(false)">
            {{ mining ? t('surface.harness.panels.genome.patterns.mining') : t('surface.harness.panels.genome.patterns.mine') }}
          </button>
          <button class="btn" data-testid="patterns-save" :disabled="mining" @click="mine(true)">
            {{ t('surface.harness.panels.genome.patterns.save') }}
          </button>
        </div>
      </div>
      <p class="patterns-meta" v-if="reflectionsScanned !== null">
        {{ t('surface.harness.panels.genome.patterns.meta', { reflections: reflectionsScanned, baseline: pctOf(baseline) }) }}
      </p>
      <p v-if="patternsError" class="err" data-testid="patterns-error">{{ patternsError }}</p>
      <p v-if="promotedSlug" class="ok">{{ t('surface.harness.panels.genome.patterns.promoted', { slug: promotedSlug }) }}</p>
      <ul v-if="suggestions.length" class="sugg-list">
        <li v-for="s in suggestions" :key="s.token" class="sugg-row">
          <span class="sugg-token">{{ s.token }}</span>
          <span class="sugg-stat">{{ pctOf(s.confirmed_rate) }} ({{ t('surface.harness.panels.genome.patterns.vsBaseline', { baseline: pctOf(s.baseline) }) }})</span>
          <span class="sugg-stat">eff {{ s.effect_size.toFixed(2) }} · q {{ s.fdr_q.toFixed(3) }}</span>
          <button
            class="btn btn-promote"
            :data-testid="`patterns-promote-${s.token}`"
            :disabled="!suggestionsSaved"
            :title="suggestionsSaved ? '' : t('surface.harness.panels.genome.patterns.saveFirst')"
            @click="promote(s)"
          >
            {{ t('surface.harness.panels.genome.patterns.promote') }}
          </button>
        </li>
      </ul>
      <span v-else-if="reflectionsScanned !== null" class="muted">{{ t('surface.harness.panels.genome.patterns.none') }}</span>
    </div>
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
.patterns { border-top: 1px solid var(--border-subtle, #2a2a36); padding-top: 0.6rem; display: flex; flex-direction: column; gap: 6px; }
.patterns-head { display: flex; justify-content: space-between; align-items: center; }
.patterns-actions { display: flex; gap: 6px; }
.patterns-meta { margin: 0; font-size: 0.75rem; color: var(--text-tertiary, #777); }
.err { color: var(--accent-red, #ef4444); font-size: 0.78rem; margin: 0; }
.ok { color: var(--accent-emerald, #22c55e); font-size: 0.78rem; margin: 0; }
.sugg-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
.sugg-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 4px 6px; background: var(--bg-tertiary, #1a1a24); border-radius: 5px; font-size: 0.78rem; }
.sugg-token { font-family: monospace; color: var(--accent-cyan, #00d4ff); }
.sugg-stat { color: var(--text-tertiary, #888); font-variant-numeric: tabular-nums; }
.btn-promote { margin-left: auto; }
</style>
