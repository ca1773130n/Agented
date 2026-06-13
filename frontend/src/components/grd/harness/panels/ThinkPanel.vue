<script setup lang="ts">
/** ThinkPanel — route 2: think (POST -> briefing). */
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../../services/api';

const props = defineProps<{ projectId: string }>();
const { t } = useI18n();
const briefing = ref<Record<string, unknown> | null>(null);
const loading = ref(false);

async function run() {
  try {
    loading.value = true;
    briefing.value = await grdHarnessApi.think(props.projectId);
  } catch {
    briefing.value = null;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="panel">
    <div class="panel-head">
      <h4>{{ t('surface.harness.panels.think.title') }}</h4>
      <button class="btn" :disabled="loading" @click="run">
        {{ t('surface.harness.panels.think.run') }}
      </button>
    </div>
    <pre v-if="briefing" class="json">{{ JSON.stringify(briefing, null, 2) }}</pre>
    <span v-else class="muted">{{ t('surface.harness.panels.think.empty') }}</span>
  </div>
</template>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 0.75rem; }
.panel-head { display: flex; justify-content: space-between; align-items: center; }
.panel-head h4 { margin: 0; font-size: 0.9rem; color: var(--text-primary, #fff); }
.json { background: var(--bg-tertiary, #1a1a24); border-radius: 6px; padding: 0.75rem; font-size: 0.75rem; overflow: auto; max-height: 320px; color: var(--text-secondary, #aaa); }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
