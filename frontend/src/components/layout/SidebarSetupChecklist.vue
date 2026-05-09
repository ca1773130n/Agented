<script setup lang="ts">
import type { ChecklistItem } from '../../composables/useTourChecklist';

defineProps<{
  items: ChecklistItem[];
  completedCount: number;
  totalCount: number;
}>();

const emit = defineEmits<{
  navigate: [path: string];
}>();
</script>

<template>
  <div class="sidebar-setup-checklist">
    <div class="setup-checklist-header">
      <span class="setup-checklist-title">Setup</span>
      <span class="setup-checklist-progress">{{ completedCount }}/{{ totalCount }}</span>
    </div>
    <ul class="setup-checklist-items">
      <li
        v-for="item in items"
        :key="item.key"
        class="setup-checklist-item"
        :class="{ completed: item.completed }"
      >
        <button
          type="button"
          class="setup-checklist-btn"
          @click="emit('navigate', item.link + (item.linkHash ?? ''))"
        >
          <span class="setup-item-icon">
            <svg v-if="item.completed" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 8l3.5 3.5L13 5"/>
            </svg>
            <svg v-else viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="8" cy="8" r="6"/>
            </svg>
          </span>
          <span class="setup-item-label">{{ item.label }}</span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.sidebar-setup-checklist {
  padding: 8px 8px 12px;
  border-top: 1px solid var(--border-subtle);
  margin-top: 4px;
}

.setup-checklist-header {
  display: flex;
  justify-content: space-between;
  padding: 4px 8px 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.setup-checklist-progress {
  color: var(--accent-cyan);
  font-variant-numeric: tabular-nums;
}

.setup-checklist-items {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.setup-checklist-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 6px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 12px;
  text-align: left;
  font-family: inherit;
  transition: background 150ms, color 150ms;
}

.setup-checklist-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.setup-checklist-item.completed .setup-checklist-btn {
  color: var(--text-tertiary);
}

.setup-item-icon svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.setup-checklist-item.completed .setup-item-icon {
  color: var(--accent-emerald);
}
</style>
