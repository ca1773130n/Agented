<script setup lang="ts">
import { computed } from 'vue'
import type { TopologyType } from '../../services/api'

const props = defineProps<{
  inferredTopology: TopologyType | null
  savedTopology?: TopologyType | null
  hasSelection?: boolean
  nodeCount?: number
}>()

// Prefer saved topology from team config; fall back to edge-based inference
const displayTopology = computed(() => props.savedTopology || props.inferredTopology)

defineEmits<{
  'auto-layout': []
  'fit-view': []
  save: []
  'delete-selected': []
  'clear-all': []
  'zoom-in': []
  'zoom-out': []
  'set-topology': [topology: string | null]
  'export-png': []
  'export-json': []
}>()

function topologyColorClass(t: string | null): string {
  if (!t) return 'none'
  return t
}
</script>

<template>
  <div class="canvas-toolbar">
    <div class="toolbar-left">
      <span class="toolbar-label">Visual Builder</span>
      <select
        class="topology-select"
        :class="topologyColorClass(displayTopology)"
        :value="displayTopology || ''"
        @change="$emit('set-topology', ($event.target as HTMLSelectElement).value || null)"
      >
        <option value="">No Topology</option>
        <option value="sequential">Sequential Pipeline</option>
        <option value="parallel">Parallel Fan-out</option>
        <option value="coordinator">Coordinator/Dispatcher</option>
        <option value="generator_critic">Generator/Critic</option>
        <option value="hierarchical">Hierarchical</option>
        <option value="human_in_loop">Human-in-Loop</option>
        <option value="composite">Composite</option>
      </select>
    </div>
    <div class="toolbar-actions">
      <button
        class="toolbar-btn"
        title="Delete selected nodes/edges"
        :disabled="!hasSelection"
        @click="$emit('delete-selected')"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 4h12M5.333 4V2.667a1.333 1.333 0 011.334-1.334h2.666a1.333 1.333 0 011.334 1.334V4M12.667 4v9.333a1.333 1.333 0 01-1.334 1.334H4.667a1.333 1.333 0 01-1.334-1.334V4" />
        </svg>
        Delete
      </button>
      <button
        class="toolbar-btn"
        title="Clear all nodes and edges"
        :disabled="!nodeCount"
        @click="$emit('clear-all')"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="12" y1="4" x2="4" y2="12" />
          <line x1="4" y1="4" x2="12" y2="12" />
        </svg>
        Clear All
      </button>
      <div class="toolbar-separator"></div>
      <button class="toolbar-btn" title="Zoom in" @click="$emit('zoom-in')">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="7" cy="7" r="5" />
          <line x1="12" y1="12" x2="14.5" y2="14.5" />
          <line x1="5" y1="7" x2="9" y2="7" />
          <line x1="7" y1="5" x2="7" y2="9" />
        </svg>
      </button>
      <button class="toolbar-btn" title="Zoom out" @click="$emit('zoom-out')">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="7" cy="7" r="5" />
          <line x1="12" y1="12" x2="14.5" y2="14.5" />
          <line x1="5" y1="7" x2="9" y2="7" />
        </svg>
      </button>
      <div class="toolbar-separator"></div>
      <button class="toolbar-btn" title="Auto-arrange nodes" @click="$emit('auto-layout')">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="1" y="1" width="5" height="5" rx="1" />
          <rect x="10" y="1" width="5" height="5" rx="1" />
          <rect x="1" y="10" width="5" height="5" rx="1" />
          <rect x="10" y="10" width="5" height="5" rx="1" />
        </svg>
        Auto Layout
      </button>
      <button class="toolbar-btn" title="Fit all nodes in view" @click="$emit('fit-view')">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M1 5V2a1 1 0 011-1h3" />
          <path d="M11 1h3a1 1 0 011 1v3" />
          <path d="M15 11v3a1 1 0 01-1 1h-3" />
          <path d="M5 15H2a1 1 0 01-1-1v-3" />
        </svg>
        Fit View
      </button>
      <button class="toolbar-btn" title="Export canvas as PNG" @click="$emit('export-png')">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="1" y="1" width="14" height="11" rx="1"/>
          <path d="M1 9l3-3 3 3 3-4 4 5"/>
        </svg>
        PNG
      </button>
      <button class="toolbar-btn" title="Export topology as JSON" @click="$emit('export-json')">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 2H2a1 1 0 00-1 1v10a1 1 0 001 1h2"/>
          <path d="M12 2h2a1 1 0 011 1v10a1 1 0 01-1 1h-2"/>
          <line x1="5" y1="8" x2="11" y2="8"/>
        </svg>
        JSON
      </button>
      <div class="toolbar-separator"></div>
      <button class="toolbar-btn primary" title="Save canvas state" @click="$emit('save')">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M13 15H3a1 1 0 01-1-1V2a1 1 0 011-1h7l4 4v9a1 1 0 01-1 1z" />
          <path d="M11 15V9H5v6" />
          <path d="M5 1v4h4" />
        </svg>
        Save
      </button>
    </div>
  </div>
</template>

<style scoped>
.canvas-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: var(--bg-secondary, #12121a);
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  flex-shrink: 0;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toolbar-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #f0f0f5);
}

.topology-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 10px;
  white-space: nowrap;
}

.topology-badge.sequential {
  background: rgba(0, 212, 255, 0.15);
  color: #00d4ff;
}

.topology-badge.parallel {
  background: rgba(0, 255, 136, 0.15);
  color: #00ff88;
}

.topology-badge.coordinator {
  background: rgba(168, 85, 247, 0.15);
  color: #a855f7;
}

.topology-badge.generator_critic {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}

.topology-badge.none {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-tertiary, #606070);
}

.topology-select {
  font-size: 11px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 10px;
  white-space: nowrap;
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  cursor: pointer;
  font-family: inherit;
  appearance: none;
  -webkit-appearance: none;
  background-repeat: no-repeat;
  background-position: right 6px center;
  background-size: 10px;
  padding-right: 22px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23a0a0b0'/%3E%3C/svg%3E");
}

.topology-select:focus {
  outline: none;
  border-color: var(--accent-cyan, #00d4ff);
}

.topology-select option {
  background: var(--bg-secondary, #12121a);
  color: var(--text-primary, #f0f0f5);
}

.topology-select.sequential {
  background-color: rgba(0, 212, 255, 0.15);
  color: #00d4ff;
}

.topology-select.parallel {
  background-color: rgba(0, 255, 136, 0.15);
  color: #00ff88;
}

.topology-select.coordinator {
  background-color: rgba(168, 85, 247, 0.15);
  color: #a855f7;
}

.topology-select.generator_critic {
  background-color: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}

.topology-select.hierarchical {
  background-color: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.topology-select.human_in_loop {
  background-color: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.topology-select.composite {
  background-color: rgba(236, 72, 153, 0.15);
  color: #ec4899;
}

.topology-select.none {
  background-color: rgba(255, 255, 255, 0.06);
  color: var(--text-tertiary, #606070);
}

.toolbar-actions {
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
  transition: background 0.15s, color 0.15s;
  font-family: inherit;
}

.toolbar-btn:hover:not(:disabled) {
  background: var(--bg-elevated, #222230);
  color: var(--text-primary, #f0f0f5);
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toolbar-btn.primary {
  background: var(--accent-cyan, #00d4ff);
  color: #000;
  border-color: transparent;
}

.toolbar-btn.primary:hover {
  opacity: 0.9;
}
</style>
