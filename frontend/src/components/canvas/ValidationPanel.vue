<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  warnings: string[]
}>()

const isCollapsed = ref(false)

watch(
  () => props.warnings,
  (newWarnings, oldWarnings) => {
    if (newWarnings.length === 0) {
      isCollapsed.value = true
    } else if (oldWarnings && oldWarnings.length === 0 && newWarnings.length > 0) {
      isCollapsed.value = false
    }
  },
)
</script>

<template>
  <div
    v-if="warnings.length > 0"
    class="validation-panel"
    :class="{ collapsed: isCollapsed }"
  >
    <div class="validation-header" @click="isCollapsed = !isCollapsed">
      <span class="warning-icon">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M7.13 1.66L1.09 12a1 1 0 00.87 1.5h12.08a1 1 0 00.87-1.5L8.87 1.66a1 1 0 00-1.74 0z" />
          <line x1="8" y1="6" x2="8" y2="9" />
          <line x1="8" y1="11.5" x2="8.01" y2="11.5" />
        </svg>
      </span>
      <span class="warning-count">{{ warnings.length }} warning{{ warnings.length > 1 ? 's' : '' }}</span>
      <span class="collapse-toggle">{{ isCollapsed ? '\u25B2' : '\u25BC' }}</span>
    </div>
    <div v-if="!isCollapsed" class="warning-list">
      <div v-for="(warning, idx) in warnings" :key="idx" class="warning-item">
        <span class="warning-bullet">\u26A0</span>
        <span class="warning-text">{{ warning }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.validation-panel {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: var(--bg-secondary, #12121a);
  border-top: 1px solid rgba(251, 191, 36, 0.3);
  z-index: 10;
  max-height: 200px;
  overflow-y: auto;
}

.validation-panel.collapsed {
  max-height: none;
  overflow: visible;
}

.validation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  cursor: pointer;
  background: rgba(251, 191, 36, 0.08);
  transition: background 0.15s;
}

.validation-header:hover {
  background: rgba(251, 191, 36, 0.12);
}

.warning-icon {
  color: #fbbf24;
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.warning-count {
  font-size: 12px;
  font-weight: 600;
  color: #fbbf24;
  flex: 1;
}

.collapse-toggle {
  font-size: 10px;
  color: var(--text-tertiary, #606070);
}

.warning-list {
  padding: 4px 0;
}

.warning-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 16px;
  font-size: 12px;
  color: var(--text-secondary, #a0a0b0);
}

.warning-bullet {
  color: #fbbf24;
  flex-shrink: 0;
}

.warning-text {
  line-height: 1.4;
}
</style>
