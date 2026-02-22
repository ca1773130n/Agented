<script setup lang="ts">
/**
 * WorkflowToolbar — Canvas toolbar with save, layout, run, and validation actions.
 *
 * Follows CanvasToolbar.vue pattern with workflow-specific controls:
 * - Left: Workflow name with dirty indicator
 * - Center: Auto-layout, validation toggle with error count badge
 * - Right: Save, Run, and Execution monitoring toggle
 */

defineProps<{
  workflowName: string
  isDirty: boolean
  isRunning: boolean
  validationErrors: number
  readOnly?: boolean
}>()

defineEmits<{
  save: []
  'auto-layout': []
  run: []
  'toggle-validation': []
  'toggle-execution': []
  back: []
  'toggle-metadata': []
}>()
</script>

<template>
  <div class="workflow-toolbar">
    <!-- Left: Back button + Workflow name + dirty indicator -->
    <div class="toolbar-left">
      <button class="toolbar-btn back-btn" title="Back to workflows" @click="$emit('back')">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M10 12L6 8l4-4" />
        </svg>
      </button>
      <span class="toolbar-label">{{ workflowName || 'Untitled Workflow' }}</span>
      <button class="toolbar-btn metadata-btn" title="Edit workflow metadata" @click="$emit('toggle-metadata')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
        </svg>
      </button>
      <span v-if="isDirty" class="dirty-badge" title="Unsaved changes">
        <span class="dirty-dot"></span>
        Unsaved
      </span>
    </div>

    <!-- Center: Layout and validation -->
    <div class="toolbar-center">
      <button
        class="toolbar-btn"
        title="Auto-arrange nodes"
        @click="$emit('auto-layout')"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <rect x="1" y="1" width="5" height="5" rx="1" />
          <rect x="10" y="1" width="5" height="5" rx="1" />
          <rect x="1" y="10" width="5" height="5" rx="1" />
          <rect x="10" y="10" width="5" height="5" rx="1" />
        </svg>
        Layout
      </button>

      <button
        class="toolbar-btn"
        :class="{ active: validationErrors > 0 }"
        title="Toggle validation panel"
        @click="$emit('toggle-validation')"
      >
        <svg
          width="16"
          height="16"
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
        Validate
        <span v-if="validationErrors > 0" class="error-count-badge">
          {{ validationErrors }}
        </span>
      </button>
    </div>

    <!-- Right: Save, Run, Execution monitoring -->
    <div class="toolbar-right">
      <button
        class="toolbar-btn"
        title="Toggle execution monitoring"
        @click="$emit('toggle-execution')"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="1 8 4 8 6 3 10 13 12 8 15 8" />
        </svg>
        Monitor
      </button>

      <div class="toolbar-separator"></div>

      <button
        class="toolbar-btn primary"
        title="Save workflow"
        :disabled="!isDirty || readOnly"
        @click="$emit('save')"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M13 15H3a1 1 0 01-1-1V2a1 1 0 011-1h7l4 4v9a1 1 0 01-1 1z" />
          <path d="M11 15V9H5v6" />
          <path d="M5 1v4h4" />
        </svg>
        Save
      </button>

      <button
        class="toolbar-btn run"
        title="Run workflow"
        :disabled="isDirty || isRunning || readOnly"
        @click="$emit('run')"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polygon points="5 3 13 8 5 13 5 3" />
        </svg>
        {{ isRunning ? 'Running...' : 'Run' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.workflow-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: var(--bg-secondary, #12121a);
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  flex-shrink: 0;
}

/* Left section */
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.back-btn {
  padding: 6px 8px;
  border: none;
  background: transparent;
}

.back-btn:hover:not(:disabled) {
  background: var(--bg-tertiary, #1a1a24);
}

.metadata-btn {
  padding: 4px 6px;
  border: none;
  background: transparent;
  opacity: 0.6;
}

.metadata-btn:hover:not(:disabled) {
  background: var(--bg-tertiary, #1a1a24);
  opacity: 1;
}

.toolbar-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #f0f0f5);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dirty-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #fbbf24;
  white-space: nowrap;
}

.dirty-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #fbbf24;
  flex-shrink: 0;
}

/* Center section */
.toolbar-center {
  display: flex;
  gap: 6px;
  align-items: center;
}

/* Right section */
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}

.toolbar-separator {
  width: 1px;
  height: 20px;
  background: var(--border-subtle, rgba(255, 255, 255, 0.06));
  margin: 0 2px;
}

/* Buttons */
.toolbar-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 6px;
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-secondary, #a0a0b0);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  font-size: 12px;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s;
  font-family: inherit;
  white-space: nowrap;
}

.toolbar-btn:hover:not(:disabled) {
  background: var(--bg-elevated, #222230);
  color: var(--text-primary, #f0f0f5);
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toolbar-btn.active {
  color: #fbbf24;
  border-color: rgba(251, 191, 36, 0.3);
}

.toolbar-btn.primary {
  background: var(--accent-cyan, #00d4ff);
  color: #000;
  border-color: transparent;
}

.toolbar-btn.primary:hover:not(:disabled) {
  opacity: 0.9;
  color: #000;
}

.toolbar-btn.primary:disabled {
  opacity: 0.3;
}

.toolbar-btn.run {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  border-color: rgba(34, 197, 94, 0.3);
}

.toolbar-btn.run:hover:not(:disabled) {
  background: rgba(34, 197, 94, 0.25);
}

.toolbar-btn.run:disabled {
  opacity: 0.3;
}

/* Error count badge */
.error-count-badge {
  font-size: 10px;
  font-weight: 700;
  min-width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  background: #ef4444;
  color: #ffffff;
}
</style>
