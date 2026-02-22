<script setup lang="ts">
defineProps<{
  title: string;
  value: string | number;
  icon?: string;
  trend?: 'up' | 'down' | 'neutral';
  color?: string;
}>();
</script>

<template>
  <div class="ds-stat-card" :style="color ? { borderLeftColor: color } : undefined">
    <div class="ds-stat-header">
      <span class="ds-stat-title">{{ title }}</span>
      <span v-if="trend" :class="['ds-stat-trend', 'ds-trend-' + trend]">
        <svg v-if="trend === 'up'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
        </svg>
        <svg v-else-if="trend === 'down'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="23 18 13.5 8.5 8.5 13.5 1 6" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
      </span>
    </div>
    <div class="ds-stat-value">{{ value }}</div>
  </div>
</template>

<style scoped>
.ds-stat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.25rem;
  border-left: 3px solid transparent;
}

.ds-stat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.ds-stat-title {
  font-size: 0.85rem;
  color: var(--text-secondary);
  font-weight: 500;
}

.ds-stat-trend svg {
  width: 16px;
  height: 16px;
}

.ds-trend-up {
  color: var(--accent-emerald, #00ff88);
}

.ds-trend-down {
  color: var(--accent-crimson, #ff4081);
}

.ds-trend-neutral {
  color: var(--text-tertiary);
}

.ds-stat-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
}
</style>
