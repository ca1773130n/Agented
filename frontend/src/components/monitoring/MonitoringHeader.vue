<script setup lang="ts">
import type { MonitoringStatus } from '../../services/api';

defineProps<{
  monitoringStatus: MonitoringStatus | null;
  monitoringRefreshing: boolean;
  pollNowLoading: boolean;
}>();

const emit = defineEmits<{
  (e: 'poll-now'): void;
}>();
</script>

<template>
  <div class="section-header">
    <h2 class="section-title">
      Rate Limit Monitoring
      <span v-if="monitoringRefreshing || pollNowLoading" class="inline-refresh-spinner"></span>
    </h2>
    <div class="monitoring-header-actions">
      <span
        v-if="monitoringStatus"
        class="monitoring-status-badge"
        :class="{ active: monitoringStatus.enabled }"
      >
        {{ monitoringStatus.enabled ? 'Active' : 'Disabled' }}
      </span>
      <button
        v-if="monitoringStatus?.enabled"
        class="check-now-btn"
        :disabled="pollNowLoading"
        @click="emit('poll-now')"
      >
        <svg v-if="!pollNowLoading" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
        <div v-else class="btn-spinner"></div>
        {{ pollNowLoading ? 'Checking...' : 'Check Now' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.section-title {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.inline-refresh-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  vertical-align: middle;
  margin-left: 8px;
}

.monitoring-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.monitoring-status-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.monitoring-status-badge.active {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}

.check-now-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.check-now-btn:hover:not(:disabled) {
  background: var(--accent-cyan);
  color: var(--bg-primary);
}

.check-now-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.check-now-btn svg {
  width: 14px;
  height: 14px;
}

.btn-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
</style>
