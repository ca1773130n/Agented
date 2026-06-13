<script setup lang="ts">
/** VerifyPanel — route 10: verifyMechanical(phase). */
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../../services/api';

const props = defineProps<{ projectId: string }>();
const { t } = useI18n();
const phase = ref('');
const result = ref<Record<string, unknown> | null>(null);
const loading = ref(false);

async function run() {
  if (!phase.value) return;
  try {
    loading.value = true;
    result.value = await grdHarnessApi.verifyMechanical(props.projectId, phase.value);
  } catch {
    result.value = null;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="panel">
    <h4>{{ t('surface.harness.panels.verify.title') }}</h4>
    <div class="form">
      <input v-model="phase" :placeholder="t('surface.harness.panels.verify.phasePlaceholder')" />
      <button class="btn" :disabled="loading" @click="run">
        {{ t('surface.harness.panels.verify.run') }}
      </button>
    </div>
    <pre v-if="result" class="json">{{ JSON.stringify(result, null, 2) }}</pre>
    <span v-else class="muted">{{ t('surface.harness.panels.verify.empty') }}</span>
  </div>
</template>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 0.75rem; }
h4 { margin: 0; font-size: 0.9rem; color: var(--text-primary, #fff); }
.form { display: flex; gap: 6px; }
.form input { flex: 1; padding: 0.5rem; background: var(--bg-tertiary, #1a1a24); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-primary, #fff); }
.json { background: var(--bg-tertiary, #1a1a24); border-radius: 6px; padding: 0.75rem; font-size: 0.75rem; overflow: auto; max-height: 320px; color: var(--text-secondary, #aaa); }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
