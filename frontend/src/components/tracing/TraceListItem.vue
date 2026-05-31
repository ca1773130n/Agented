<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { Trace } from '../../services/api/tracing';

const { t } = useI18n();

defineProps<{ trace: Trace }>();
</script>

<template>
  <RouterLink
    class="trace-row"
    :to="{ name: 'trace-detail', params: { id: trace.id } }"
  >
    <span class="trace-name">{{ trace.name }}</span>
    <span class="trace-entity">{{ trace.entity_type }}:{{ trace.entity_id }}</span>
    <span
      class="trace-status"
      :class="`status-${trace.status}`"
      data-testid="trace-status"
    >{{ trace.status }}</span>
    <span class="trace-started">{{ trace.started_at }}</span>
    <span class="trace-duration" data-testid="trace-duration">
      {{ trace.duration_ms != null ? `${trace.duration_ms}ms` : t('traceListItem.running') }}
    </span>
  </RouterLink>
</template>

<style scoped>
.trace-row {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
  text-decoration: none;
  color: inherit;
}
.trace-row:hover { background: var(--bg-tertiary); }
.trace-name { font-weight: 600; flex: 1; }
.trace-entity { color: var(--text-tertiary); font-size: 12px; }
.trace-status { padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.status-running { background: rgba(96, 165, 250, 0.15); color: var(--accent-cyan, #60a5fa); }
.status-completed { background: rgba(16, 185, 129, 0.15); color: var(--accent-green, #10b981); }
.status-error { background: rgba(239, 68, 68, 0.15); color: var(--accent-red, #ef4444); }
.trace-started { color: var(--text-tertiary); font-size: 11px; }
.trace-duration { color: var(--text-tertiary); font-size: 11px; min-width: 80px; text-align: right; }
</style>
