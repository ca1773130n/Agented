<script setup lang="ts">
/**
 * WorkflowValidationPanel — Displays validation results at the bottom of the canvas.
 *
 * Follows ValidationPanel.vue pattern with enhanced support for error vs warning
 * levels and clickable results that highlight affected nodes.
 */

import { ref, computed, watch } from 'vue'
import type { ValidationResult } from '../../composables/useWorkflowValidation'

const props = defineProps<{
  results: ValidationResult[]
  visible: boolean
}>()

defineEmits<{
  close: []
  'highlight-nodes': [nodeIds: string[]]
}>()

const isCollapsed = ref(false)

// Auto-expand when new issues appear, auto-collapse when cleared
watch(
  () => props.results,
  (newResults, oldResults) => {
    if (newResults.length === 0) {
      isCollapsed.value = true
    } else if (oldResults && oldResults.length === 0 && newResults.length > 0) {
      isCollapsed.value = false
    }
  },
)

const errorCount = computed(
  () => props.results.filter((r) => r.level === 'error').length,
)

const warningCount = computed(
  () => props.results.filter((r) => r.level === 'warning').length,
)
</script>

<template>
  <div
    v-if="visible && results.length > 0"
    class="validation-panel"
    :class="{ collapsed: isCollapsed }"
  >
    <div class="validation-header" @click="isCollapsed = !isCollapsed">
      <div class="header-summary">
        <span v-if="errorCount > 0" class="count-badge error">
          <svg
            width="12"
            height="12"
            viewBox="0 0 16 16"
            fill="currentColor"
          >
            <circle cx="8" cy="8" r="7" />
          </svg>
          {{ errorCount }} error{{ errorCount > 1 ? 's' : '' }}
        </span>
        <span v-if="warningCount > 0" class="count-badge warning">
          <svg
            width="12"
            height="12"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path
              d="M7.13 1.66L1.09 12a1 1 0 00.87 1.5h12.08a1 1 0 00.87-1.5L8.87 1.66a1 1 0 00-1.74 0z"
            />
          </svg>
          {{ warningCount }} warning{{ warningCount > 1 ? 's' : '' }}
        </span>
      </div>
      <div class="header-actions">
        <span class="collapse-toggle">{{ isCollapsed ? '\u25B2' : '\u25BC' }}</span>
        <button
          class="close-btn"
          title="Close validation panel"
          @click.stop="$emit('close')"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <line x1="12" y1="4" x2="4" y2="12" />
            <line x1="4" y1="4" x2="12" y2="12" />
          </svg>
        </button>
      </div>
    </div>

    <div v-if="!isCollapsed" class="result-list">
      <div
        v-for="(result, idx) in results"
        :key="idx"
        :class="['result-item', result.level]"
        :role="result.nodeIds?.length ? 'button' : undefined"
        :tabindex="result.nodeIds?.length ? 0 : undefined"
        @click="result.nodeIds?.length && $emit('highlight-nodes', result.nodeIds!)"
        @keydown.enter="
          result.nodeIds?.length && $emit('highlight-nodes', result.nodeIds!)
        "
      >
        <!-- Error icon -->
        <span v-if="result.level === 'error'" class="result-icon error-icon">
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <circle cx="8" cy="8" r="7" />
            <line x1="10" y1="6" x2="6" y2="10" />
            <line x1="6" y1="6" x2="10" y2="10" />
          </svg>
        </span>
        <!-- Warning icon -->
        <span v-else class="result-icon warning-icon">
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path
              d="M7.13 1.66L1.09 12a1 1 0 00.87 1.5h12.08a1 1 0 00.87-1.5L8.87 1.66a1 1 0 00-1.74 0z"
            />
            <line x1="8" y1="6" x2="8" y2="9" />
            <line x1="8" y1="11.5" x2="8.01" y2="11.5" />
          </svg>
        </span>
        <span class="result-text">{{ result.message }}</span>
        <span
          v-if="result.nodeIds?.length"
          class="result-hint"
        >
          Click to highlight
        </span>
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
  border-top: 1px solid rgba(239, 68, 68, 0.3);
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
  justify-content: space-between;
  padding: 8px 16px;
  cursor: pointer;
  background: rgba(239, 68, 68, 0.06);
  transition: background 0.15s;
}

.validation-header:hover {
  background: rgba(239, 68, 68, 0.1);
}

.header-summary {
  display: flex;
  align-items: center;
  gap: 12px;
}

.count-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
}

.count-badge.error {
  color: #ef4444;
}

.count-badge.warning {
  color: #fbbf24;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.collapse-toggle {
  font-size: 10px;
  color: var(--text-tertiary, #606070);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-tertiary, #606070);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  transition: color 0.15s;
}

.close-btn:hover {
  color: var(--text-primary, #f0f0f5);
}

.result-list {
  padding: 4px 0;
}

.result-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 16px;
  font-size: 12px;
  color: var(--text-secondary, #a0a0b0);
  transition: background 0.15s;
}

.result-item[role='button'] {
  cursor: pointer;
}

.result-item[role='button']:hover {
  background: rgba(255, 255, 255, 0.03);
}

.result-icon {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  margin-top: 1px;
}

.error-icon {
  color: #ef4444;
}

.warning-icon {
  color: #fbbf24;
}

.result-text {
  line-height: 1.4;
  flex: 1;
}

.result-hint {
  font-size: 10px;
  color: var(--text-tertiary, #606070);
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
