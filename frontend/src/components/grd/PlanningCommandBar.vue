<script setup lang="ts">
defineProps<{
  status: 'idle' | 'running' | 'waiting_input' | 'complete' | 'error';
  grdInitStatus: string;
}>();

const emit = defineEmits<{
  invoke: [command: string, args?: Record<string, string>];
}>();

const commandGroups = [
  {
    label: 'Project Setup',
    commands: [
      { name: 'map-codebase', label: 'Map Codebase', description: 'Analyze project structure' },
      { name: 'new-milestone', label: 'New Milestone', description: 'Create a new milestone' },
      {
        name: 'long-term-roadmap',
        label: 'Long-term Roadmap',
        description: 'Generate strategic roadmap',
      },
    ],
  },
  {
    label: 'Phase Management',
    commands: [
      { name: 'add-phase', label: 'Add Phase', description: 'Add a phase to milestone' },
      { name: 'remove-phase', label: 'Remove Phase', description: 'Remove a phase' },
      { name: 'insert-phase', label: 'Insert Phase', description: 'Insert phase at position' },
      {
        name: 'discuss-phase',
        label: 'Discuss Phase',
        description: 'AI-assisted phase discussion',
      },
      { name: 'plan-phase', label: 'Plan Phase', description: 'Generate execution plans' },
    ],
  },
  {
    label: 'Research & Analysis',
    commands: [
      { name: 'survey', label: 'Survey', description: 'Survey research landscape' },
      { name: 'deep-dive', label: 'Deep Dive', description: 'Deep dive into topic' },
      { name: 'feasibility', label: 'Feasibility', description: 'Assess feasibility' },
      {
        name: 'assess-baseline',
        label: 'Assess Baseline',
        description: 'Establish performance baseline',
      },
      { name: 'compare-methods', label: 'Compare Methods', description: 'Compare approaches' },
      {
        name: 'list-phase-assumptions',
        label: 'List Assumptions',
        description: 'Surface phase assumptions',
      },
    ],
  },
  {
    label: 'Requirements',
    commands: [
      { name: 'requirement', label: 'Requirement', description: 'Define a requirement' },
      {
        name: 'plan-milestone-gaps',
        label: 'Plan Gaps',
        description: 'Identify milestone gaps',
      },
      {
        name: 'complete-milestone',
        label: 'Complete Milestone',
        description: 'Mark milestone complete',
      },
    ],
  },
] as const;

const isDisabled = (status: string) => status === 'running' || status === 'waiting_input';

function handleClick(commandName: string) {
  emit('invoke', commandName);
}
</script>

<template>
  <div class="command-bar">
    <div class="command-bar-header">
      <h3 class="command-bar-title">Planning Commands</h3>
      <span v-if="grdInitStatus !== 'none'" class="init-status" :class="'init-' + grdInitStatus">
        {{ grdInitStatus }}
      </span>
    </div>

    <div v-for="group in commandGroups" :key="group.label" class="command-group">
      <div class="group-label">{{ group.label }}</div>
      <div class="command-grid">
        <button
          v-for="cmd in group.commands"
          :key="cmd.name"
          class="command-btn"
          :disabled="isDisabled(status)"
          :title="cmd.description"
          @click="handleClick(cmd.name)"
        >
          {{ cmd.label }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.command-bar {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 16px;
}

.command-bar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.command-bar-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.init-status {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.init-ready {
  color: var(--accent-emerald);
  background: rgba(0, 255, 136, 0.1);
}

.init-initializing {
  color: var(--accent-cyan);
  background: rgba(0, 180, 216, 0.1);
}

.init-failed {
  color: var(--accent-crimson, #ff4081);
  background: rgba(255, 64, 129, 0.1);
}

.command-group {
  margin-bottom: 14px;
}

.command-group:last-child {
  margin-bottom: 0;
}

.group-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.command-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.command-btn {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.command-btn:hover:not(:disabled) {
  color: var(--text-primary);
  border-color: var(--accent-cyan);
  background: var(--accent-cyan-dim, rgba(0, 180, 216, 0.08));
}

.command-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
