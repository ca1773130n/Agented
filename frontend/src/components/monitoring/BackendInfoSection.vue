<template>
  <div class="backend-info-section">
    <div class="info-grid">
      <div class="info-card">
        <h3>{{ t('backendDetail.availableModels') }}</h3>
        <div class="model-tags">
          <span v-for="model in models" :key="model" class="model-tag">
            {{ model }}
          </span>
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
import { useI18n } from 'vue-i18n';

interface CapabilityItem {
  label: string;
  supported: boolean;
  flag: string | null;
}

defineProps<{
  models: string[];
  capabilityList: CapabilityItem[];
  cliPath: string | null;
}>();

const { t } = useI18n();
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
