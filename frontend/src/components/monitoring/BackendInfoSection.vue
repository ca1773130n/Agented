<template>
  <div class="backend-info-section">
    <div class="info-grid">
      <div class="info-card">
        <div class="info-card-header">
          <h3>{{ t('backendDetail.availableModels') }}</h3>
          <button
            v-if="backendKind"
            type="button"
            class="refresh-btn"
            :disabled="refreshing"
            data-testid="refresh-models-btn"
            :title="t('backendDetail.refreshModelsTooltip', 'Re-discover models')"
            @click="onRefreshClick"
          >
            <span v-if="refreshing" class="spinner" data-testid="refresh-spinner" />
            <span v-else aria-hidden="true">&#x21bb;</span>
            <span class="refresh-label">
              {{ refreshing
                  ? t('backendDetail.refreshingModels', 'Refreshing…')
                  : t('backendDetail.refreshModels', 'Refresh models')
              }}
            </span>
          </button>
        </div>
        <div class="model-tags">
          <span v-for="model in localModels" :key="model" class="model-tag">
            {{ model }}
          </span>
        </div>
        <div v-if="discoveredAtLabel" class="discovered-at" data-testid="discovered-at">
          {{ discoveredAtLabel }}
        </div>
        <div v-if="refreshError" class="refresh-error" role="alert" data-testid="refresh-error">
          {{ refreshError }}
        </div>
      </div>
      <div v-if="capabilityList.length > 0" class="info-card capabilities-card">
        <h3>{{ t('backendDetail.capabilities') }}</h3>
        <div class="capabilities-list">
          <div v-for="cap in capabilityList" :key="cap.label" class="capability-item">
            <span class="capability-dot" :class="{ active: cap.supported }"></span>
            <span class="capability-label">{{ cap.label }}</span>
            <span v-if="cap.flag" class="capability-flag">{{ cap.flag }}</span>
          </div>
        </div>
      </div>
      <div v-if="cliPath" class="info-card">
        <h3>{{ t('backendDetail.cliPath') }}</h3>
        <code class="cli-path-value">{{ cliPath }}</code>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { modelCacheApi } from '../../services/api/model-cache';

interface CapabilityItem {
  label: string;
  supported: boolean;
  flag: string | null;
}

const props = defineProps<{
  models: string[];
  capabilityList: CapabilityItem[];
  cliPath: string | null;
  backendKind?: string;
  authMethod?: string;
}>();

const emit = defineEmits<{
  (e: 'models-refreshed', payload: { models: string[]; discoveredAt: string }): void;
}>();

const { t } = useI18n();

// Local override of models so the refresh button can update the UI
// without requiring the parent to re-fetch.
const localModels = ref<string[]>([...props.models]);
const discoveredAt = ref<string | null>(null);
const refreshing = ref(false);
const refreshError = ref<string | null>(null);

watch(
  () => props.models,
  (next) => {
    localModels.value = [...next];
  },
);

const discoveredAtLabel = computed(() => {
  if (!discoveredAt.value) return '';
  const then = Date.parse(discoveredAt.value);
  if (Number.isNaN(then)) return '';
  const seconds = Math.max(1, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) {
    return t('backendDetail.discoveredSecondsAgo', { count: seconds }, `discovered ${seconds}s ago`);
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return t('backendDetail.discoveredMinutesAgo', { count: minutes }, `discovered ${minutes}m ago`);
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return t('backendDetail.discoveredHoursAgo', { count: hours }, `discovered ${hours}h ago`);
  }
  const days = Math.floor(hours / 24);
  return t('backendDetail.discoveredDaysAgo', { count: days }, `discovered ${days}d ago`);
});

async function onRefreshClick() {
  if (!props.backendKind || refreshing.value) return;
  refreshing.value = true;
  refreshError.value = null;
  try {
    const resp = await modelCacheApi.refresh(
      props.backendKind,
      props.authMethod ?? 'unknown',
    );
    // Refresh endpoint returns meta only; pull the fresh model list.
    const listResp = await modelCacheApi.list(
      props.backendKind,
      props.authMethod ?? 'unknown',
    );
    localModels.value = listResp.models;
    discoveredAt.value = resp.discovered_at ?? listResp.discovered_at;
    if (resp.error_message) {
      refreshError.value = resp.error_message;
    }
    emit('models-refreshed', {
      models: listResp.models,
      discoveredAt: discoveredAt.value ?? '',
    });
  } catch (e) {
    refreshError.value = e instanceof Error ? e.message : String(e);
  } finally {
    refreshing.value = false;
  }
}
</script>

<style scoped>
.backend-info-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 2rem;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.info-card {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 1rem;
}

.info-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.info-card-header h3 {
  margin: 0;
}

.info-card h3 {
  margin: 0 0 0.5rem 0;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  font-weight: 500;
}

.info-card p {
  margin: 0;
  font-size: 1rem;
  color: var(--text-primary);
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.625rem;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s ease;
}

.refresh-btn:hover:not(:disabled) {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid var(--text-tertiary);
  border-top-color: var(--accent-violet);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.refresh-label {
  font-weight: 500;
}

.discovered-at {
  margin-top: 0.5rem;
  font-size: 0.6875rem;
  color: var(--text-tertiary);
}

.refresh-error {
  margin-top: 0.5rem;
  padding: 0.375rem 0.5rem;
  font-size: 0.75rem;
  color: var(--accent-rose, #ef4444);
  background: var(--accent-rose-dim, rgba(239, 68, 68, 0.1));
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: 4px;
}

.model-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.model-tag {
  padding: 0.25rem 0.75rem;
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
  border: 1px solid rgba(136, 85, 255, 0.25);
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
  font-family: var(--font-mono);
}

/* Capabilities */
.capabilities-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.capability-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.capability-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-tertiary);
  flex-shrink: 0;
}

.capability-dot.active {
  background: var(--accent-emerald);
  box-shadow: 0 0 4px var(--accent-emerald-dim);
}

.capability-label {
  color: var(--text-primary);
}

.capability-flag {
  font-family: monospace;
  font-size: 0.75rem;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
}

.cli-path-value {
  display: block;
  padding: 0.375rem 0.5rem;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.8125rem;
  color: var(--text-primary);
  word-break: break-all;
}
</style>
