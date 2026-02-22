<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';

/**
 * ProcessGroup renders a collapsible section for tool calls,
 * reasoning blocks, or code executions in the chat stream.
 * Features auto-collapse with configurable timers that are
 * cancelled on mouseenter and rescheduled on mouseleave.
 */

const props = withDefaults(
  defineProps<{
    id: string;
    type: 'tool_call' | 'reasoning' | 'code_execution';
    label: string;
    timestamp: string;
    autoCollapseMs: number;
  }>(),
  {
    autoCollapseMs: 0,
  },
);

const isExpanded = ref(true);
const isHovered = ref(false);
let collapseTimer: ReturnType<typeof setTimeout> | null = null;

function toggle() {
  isExpanded.value = !isExpanded.value;
}

function scheduleCollapse() {
  if (props.autoCollapseMs > 0 && !isHovered.value) {
    collapseTimer = setTimeout(() => {
      isExpanded.value = false;
    }, props.autoCollapseMs);
  }
}

function cancelCollapse() {
  if (collapseTimer !== null) {
    clearTimeout(collapseTimer);
    collapseTimer = null;
  }
}

function onMouseEnter() {
  isHovered.value = true;
  cancelCollapse();
}

function onMouseLeave() {
  isHovered.value = false;
  scheduleCollapse();
}

onMounted(() => {
  scheduleCollapse();
});

onUnmounted(() => {
  cancelCollapse();
});

/** Compute a display label for the type badge */
function typeBadgeLabel(type: string): string {
  switch (type) {
    case 'tool_call': return 'Tool';
    case 'reasoning': return 'Thinking';
    case 'code_execution': return 'Code';
    default: return type;
  }
}
</script>

<template>
  <div
    :class="['process-group', `process-group--${type}`]"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
  >
    <div class="process-group__header" @click="toggle">
      <span :class="['process-group__badge', `badge--${type}`]">
        <!-- Wrench icon for tool_call -->
        <svg v-if="type === 'tool_call'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>
        </svg>
        <!-- Brain icon for reasoning -->
        <svg v-else-if="type === 'reasoning'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2a8 8 0 018 8c0 3-2 5.5-4 7l-1 4H9l-1-4c-2-1.5-4-4-4-7a8 8 0 018-8z"/>
          <path d="M9 21h6M10 17h4"/>
        </svg>
        <!-- Terminal icon for code_execution -->
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="4 17 10 11 4 5"/>
          <line x1="12" y1="19" x2="20" y2="19"/>
        </svg>
        {{ typeBadgeLabel(type) }}
      </span>
      <span class="process-group__label">{{ label }}</span>
      <span class="process-group__time">{{ new Date(timestamp).toLocaleTimeString() }}</span>
      <span :class="['process-group__chevron', { expanded: isExpanded }]">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </span>
    </div>
    <div class="process-group__body" v-show="isExpanded">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.process-group {
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background: var(--bg-tertiary);
  overflow: hidden;
  margin: 4px 0;
}

/* Header */
.process-group__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.process-group__header:hover {
  background: var(--bg-elevated, rgba(255, 255, 255, 0.03));
}

/* Type badges with distinct colors */
.process-group__badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  flex-shrink: 0;
}

.process-group__badge svg {
  width: 12px;
  height: 12px;
}

/* Cyan for tool_call */
.badge--tool_call {
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15));
  color: var(--accent-cyan, #00d4ff);
}

/* Violet for reasoning */
.badge--reasoning {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  color: var(--accent-violet, #8855ff);
}

/* Amber for code_execution */
.badge--code_execution {
  background: rgba(255, 193, 7, 0.15);
  color: #ffc107;
}

.process-group__label {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.process-group__time {
  font-size: 11px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.process-group__chevron {
  display: flex;
  align-items: center;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.process-group__chevron svg {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
}

.process-group__chevron.expanded {
  transform: rotate(0deg);
}

.process-group__chevron:not(.expanded) {
  transform: rotate(-90deg);
}

/* Body with smooth expand/collapse transition */
.process-group__body {
  padding: 8px 12px;
  border-top: 1px solid var(--border-default);
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}
</style>
