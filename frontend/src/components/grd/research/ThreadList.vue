<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { ResearchThread } from '../../../services/api/research';

defineProps<{
  threads: ResearchThread[];
  selectedId?: string | null;
}>();

const emit = defineEmits<{
  (e: 'select', id: string): void;
}>();

const { t } = useI18n();

function statusLabel(status: string): string {
  const key = `surface.research.status.${status}`;
  const translated = t(key);
  // vue-i18n returns the key itself when missing — fall back to the raw status.
  return translated === key ? status : translated;
}

defineExpose({ statusLabel });
</script>

<template>
  <div class="thread-list">
    <h3 class="tl-title">{{ t('surface.research.threads.title') }}</h3>
    <p v-if="threads.length === 0" class="tl-empty">
      {{ t('surface.research.threads.empty') }}
    </p>
    <table v-else class="tl-table">
      <thead>
        <tr>
          <th>{{ t('surface.research.threads.question') }}</th>
          <th>{{ t('surface.research.threads.status') }}</th>
          <th>{{ t('surface.research.threads.iteration') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="thread in threads"
          :key="thread.id"
          class="tl-row"
          :class="{ selected: thread.id === selectedId }"
          @click="emit('select', thread.id)"
        >
          <td class="tl-question">{{ thread.question }}</td>
          <td>
            <span
              v-if="thread.status === 'paused'"
              class="tl-status tl-status--paused"
              data-status="paused"
              data-testid="tl-paused-badge"
            >{{ t('researchCheckpoint.pausedBadge') }}</span>
            <span v-else class="tl-status" :data-status="thread.status">{{ statusLabel(thread.status) }}</span>
          </td>
          <td class="tl-iter">{{ thread.iteration }} / {{ thread.max_iterations }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.thread-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tl-title {
  font-size: 0.95rem;
  margin: 0;
}
.tl-empty {
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.tl-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.tl-table th {
  text-align: left;
  padding: 6px 8px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-default);
}
.tl-row {
  cursor: pointer;
}
.tl-row td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border-subtle, var(--border-default));
}
.tl-row.selected {
  background: var(--bg-tertiary);
}
.tl-status {
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-tertiary);
  font-size: 0.75rem;
}
.tl-status--paused {
  color: var(--text-on-accent, #fff);
  background: var(--accent-color, var(--accent-cyan));
  font-weight: 600;
  white-space: nowrap;
}
.tl-iter {
  white-space: nowrap;
  color: var(--text-secondary);
}
</style>
