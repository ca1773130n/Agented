<script setup lang="ts">
/** HealthPanel — route 1: getHealth. */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../../services/api';

const props = defineProps<{ projectId: string }>();
const { t } = useI18n();
const data = ref<Record<string, unknown> | null>(null);
const loading = ref(false);

async function load() {
  try {
    loading.value = true;
    data.value = await grdHarnessApi.getHealth(props.projectId);
  } catch {
    data.value = null;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>

<template>
  <div class="panel">
    <div class="panel-head">
      <h4>{{ t('surface.harness.panels.health.title') }}</h4>
      <button class="btn" @click="load">{{ t('surface.harness.panels.health.refresh') }}</button>
    </div>
    <pre v-if="data" class="json">{{ JSON.stringify(data, null, 2) }}</pre>
    <span v-else class="muted">{{ t('surface.harness.panels.health.empty') }}</span>
  </div>
</template>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 0.75rem; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-head h4 { margin: 0; font-size: 0.9rem; color: var(--text-primary, #fff); }
.json { background: var(--bg-tertiary, #1a1a24); border-radius: 6px; padding: 0.75rem; font-size: 0.75rem; overflow: auto; max-height: 320px; color: var(--text-secondary, #aaa); }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
