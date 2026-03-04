<script setup lang="ts">
import { ref, computed } from 'vue';
import { formatDistanceToNow } from 'date-fns';
import type { HealthAlert } from '../../services/api';

const props = defineProps<{
  alerts: HealthAlert[];
}>();

const emit = defineEmits<{
  acknowledge: [alertId: number];
}>();

type FilterType = 'all' | 'critical' | 'warning' | 'acknowledged';
const activeFilter = ref<FilterType>('all');

const filteredAlerts = computed(() => {
  switch (activeFilter.value) {
    case 'critical':
      return props.alerts.filter(a => a.severity === 'critical' && !a.acknowledged);
    case 'warning':
      return props.alerts.filter(a => a.severity === 'warning' && !a.acknowledged);
    case 'acknowledged':
      return props.alerts.filter(a => a.acknowledged);
    default:
      return props.alerts;
  }
});

const alertTypeLabels: Record<string, string> = {
  consecutive_failure: 'Failing',
  slow_execution: 'Slow',
  missing_fire: 'Missing',
  budget_exceeded: 'Budget',
};

function getAlertTypeLabel(type: string): string {
  return alertTypeLabels[type] || type;
}

function formatRelativeTime(dateStr: string): string {
  try {
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
  } catch {
    return dateStr;
  }
}
</script>

<template>
  <div class="health-alert-list">
    <!-- Filter pills -->
    <div class="filter-pills">
      <button
        v-for="filter in (['all', 'critical', 'warning', 'acknowledged'] as FilterType[])"
        :key="filter"
        class="filter-pill"
        :class="{ active: activeFilter === filter }"
        @click="activeFilter = filter"
      >
        {{ filter === 'all' ? 'All' : filter.charAt(0).toUpperCase() + filter.slice(1) }}
        <span v-if="filter === 'critical'" class="filter-count critical">
          {{ alerts.filter(a => a.severity === 'critical' && !a.acknowledged).length }}
        </span>
        <span v-else-if="filter === 'warning'" class="filter-count warning">
          {{ alerts.filter(a => a.severity === 'warning' && !a.acknowledged).length }}
        </span>
      </button>
    </div>

    <!-- Empty state -->
    <div v-if="filteredAlerts.length === 0" class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
        <polyline points="22 4 12 14.01 9 11.01"/>
      </svg>
      <p>No health alerts. All bots are running normally.</p>
    </div>

    <!-- Alert cards -->
    <div v-else class="alerts-container">
      <div
        v-for="alert in filteredAlerts"
        :key="alert.id"
        class="alert-card"
        :class="[alert.severity, { acknowledged: alert.acknowledged }]"
      >
        <div class="alert-severity-indicator" :class="alert.severity"></div>
        <div class="alert-content">
          <div class="alert-header">
            <span class="alert-type-badge" :class="alert.alert_type">
              {{ getAlertTypeLabel(alert.alert_type) }}
            </span>
            <span class="alert-severity-badge" :class="alert.severity">
              {{ alert.severity }}
            </span>
            <span class="alert-time">{{ formatRelativeTime(alert.created_at) }}</span>
          </div>
          <div class="alert-trigger">{{ alert.trigger_id }}</div>
          <div class="alert-message">{{ alert.message }}</div>
          <div v-if="alert.details" class="alert-details">{{ alert.details }}</div>
        </div>
        <div class="alert-actions">
          <button
            v-if="!alert.acknowledged"
            class="btn-acknowledge"
            title="Acknowledge this alert"
            @click="emit('acknowledge', alert.id)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </button>
          <span v-else class="acknowledged-badge">Acknowledged</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.health-alert-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 500;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.filter-pill:hover {
  border-color: var(--border-default);
  color: var(--text-primary);
}

.filter-pill.active {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.filter-count {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--bg-elevated);
}

.filter-count.critical {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.filter-count.warning {
  background: var(--accent-amber-dim, rgba(245, 158, 11, 0.15));
  color: var(--accent-amber);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 24px;
  color: var(--text-tertiary);
  text-align: center;
}

.empty-state svg {
  width: 40px;
  height: 40px;
  color: var(--accent-emerald);
  opacity: 0.6;
}

.empty-state p {
  font-size: 0.9rem;
}

.alerts-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.alert-card {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px 20px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  transition: all var(--transition-fast);
}

.alert-card.critical {
  border-left: 3px solid var(--accent-crimson);
}

.alert-card.warning {
  border-left: 3px solid var(--accent-amber);
}

.alert-card.acknowledged {
  opacity: 0.6;
}

.alert-severity-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 6px;
  flex-shrink: 0;
}

.alert-severity-indicator.critical {
  background: var(--accent-crimson);
  box-shadow: 0 0 6px var(--accent-crimson);
}

.alert-severity-indicator.warning {
  background: var(--accent-amber);
  box-shadow: 0 0 6px var(--accent-amber);
}

.alert-content {
  flex: 1;
  min-width: 0;
}

.alert-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.alert-type-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  background: var(--bg-elevated);
  color: var(--text-secondary);
}

.alert-type-badge.consecutive_failure {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.alert-type-badge.slow_execution {
  background: var(--accent-amber-dim, rgba(245, 158, 11, 0.15));
  color: var(--accent-amber);
}

.alert-type-badge.missing_fire {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.alert-type-badge.budget_exceeded {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.alert-severity-badge {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.alert-severity-badge.critical {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.alert-severity-badge.warning {
  background: var(--accent-amber-dim, rgba(245, 158, 11, 0.15));
  color: var(--accent-amber);
}

.alert-time {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-left: auto;
}

.alert-trigger {
  font-size: 0.8rem;
  font-family: var(--font-mono);
  color: var(--accent-cyan);
  margin-bottom: 4px;
}

.alert-message {
  font-size: 0.85rem;
  color: var(--text-primary);
  line-height: 1.4;
}

.alert-details {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  margin-top: 4px;
  font-family: var(--font-mono);
}

.alert-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.btn-acknowledge {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--text-tertiary);
}

.btn-acknowledge:hover {
  background: var(--accent-emerald-dim);
  border-color: var(--accent-emerald);
  color: var(--accent-emerald);
}

.btn-acknowledge svg {
  width: 16px;
  height: 16px;
}

.acknowledged-badge {
  font-size: 0.7rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
</style>
