<script setup lang="ts">
import { ref } from 'vue';

const props = defineProps<{
  phaseNumber: number;
  phaseName: string;
  planCount: number;
  initialCollapsed?: boolean;
}>();

const isCollapsed = ref(props.initialCollapsed ?? false);
</script>

<template>
  <div class="phase-swimlane" :class="{ collapsed: isCollapsed }">
    <div class="swimlane-header" @click="isCollapsed = !isCollapsed">
      <svg
        class="chevron"
        :class="{ open: !isCollapsed }"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M9 18l6-6-6-6" />
      </svg>
      <span class="phase-label">Phase {{ phaseNumber }}: {{ phaseName }}</span>
      <span class="phase-count">{{ planCount }}</span>
    </div>
    <div v-show="!isCollapsed" class="swimlane-body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.phase-swimlane {
  margin-bottom: 4px;
}

.swimlane-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  cursor: pointer;
  border-radius: 6px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background var(--transition-fast);
  user-select: none;
}

.swimlane-header:hover {
  background: var(--bg-hover, var(--bg-elevated));
}

.chevron {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--text-tertiary);
  transition: transform 0.2s;
  transform: rotate(0deg);
}

.chevron.open {
  transform: rotate(90deg);
}

.phase-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.phase-count {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.swimlane-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
}
</style>
