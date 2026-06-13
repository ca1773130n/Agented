<script setup lang="ts">
/** ReflectionsPanel — routes 11,12: listPhaseReflections(phase), verdictCounts. */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../../services/api';

const props = defineProps<{ projectId: string }>();
const { t } = useI18n();

const phase = ref('');
const reflections = ref<unknown[]>([]);
const verdicts = ref<Record<string, unknown> | null>(null);

async function loadVerdicts() {
  try {
    verdicts.value = await grdHarnessApi.verdictCounts(props.projectId);
  } catch {
    verdicts.value = null;
  }
}

async function loadReflections() {
  if (!phase.value) return;
  try {
    const res = await grdHarnessApi.listPhaseReflections(props.projectId, phase.value);
    reflections.value = res.reflections || [];
  } catch {
    reflections.value = [];
  }
}

onMounted(loadVerdicts);
</script>

<template>
  <div class="panel">
    <h4>{{ t('surface.harness.panels.reflections.title') }}</h4>
    <div class="form">
      <input
        v-model="phase"
        :placeholder="t('surface.harness.panels.reflections.phasePlaceholder')"
      />
      <button class="btn" @click="loadReflections">
        {{ t('surface.harness.panels.reflections.load') }}
      </button>
    </div>
    <div class="sub">
      <span class="lbl">{{ t('surface.harness.panels.reflections.verdicts') }}</span>
      <pre v-if="verdicts" class="json">{{ JSON.stringify(verdicts, null, 2) }}</pre>
    </div>
    <ul v-if="reflections.length" class="rows">
      <li v-for="(r, i) in reflections" :key="i" class="row">{{ JSON.stringify(r) }}</li>
    </ul>
    <span v-else class="muted">{{ t('surface.harness.panels.reflections.empty') }}</span>
  </div>
</template>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 0.75rem; }
h4 { margin: 0; font-size: 0.9rem; color: var(--text-primary, #fff); }
.form { display: flex; gap: 6px; }
.form input { flex: 1; padding: 0.5rem; background: var(--bg-tertiary, #1a1a24); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-primary, #fff); }
.sub { display: flex; flex-direction: column; gap: 4px; }
.lbl { color: var(--text-tertiary, #888); font-size: 0.8rem; }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.row { padding: 0.4rem; background: var(--bg-tertiary, #1a1a24); border-radius: 6px; font-size: 0.75rem; color: var(--text-secondary, #aaa); }
.json { background: var(--bg-tertiary, #1a1a24); border-radius: 6px; padding: 0.75rem; font-size: 0.75rem; overflow: auto; max-height: 200px; color: var(--text-secondary, #aaa); }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
