<script setup lang="ts">
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

defineProps<{
  status: 'idle' | 'running' | 'waiting_input' | 'complete' | 'error';
  grdInitStatus: string;
}>();

const emit = defineEmits<{
  invoke: [command: string, args?: Record<string, string>];
}>();

const commandGroups = [
  {
    labelKey: 'planningCommandBar.groups.projectSetup',
    commands: [
      { name: 'map-codebase', labelKey: 'planningCommandBar.cmd.mapCodebase.label', descKey: 'planningCommandBar.cmd.mapCodebase.desc' },
      { name: 'new-milestone', labelKey: 'planningCommandBar.cmd.newMilestone.label', descKey: 'planningCommandBar.cmd.newMilestone.desc' },
      { name: 'long-term-roadmap', labelKey: 'planningCommandBar.cmd.longTermRoadmap.label', descKey: 'planningCommandBar.cmd.longTermRoadmap.desc' },
    ],
  },
  {
    labelKey: 'planningCommandBar.groups.phaseManagement',
    commands: [
      { name: 'add-phase', labelKey: 'planningCommandBar.cmd.addPhase.label', descKey: 'planningCommandBar.cmd.addPhase.desc' },
      { name: 'remove-phase', labelKey: 'planningCommandBar.cmd.removePhase.label', descKey: 'planningCommandBar.cmd.removePhase.desc' },
      { name: 'insert-phase', labelKey: 'planningCommandBar.cmd.insertPhase.label', descKey: 'planningCommandBar.cmd.insertPhase.desc' },
      { name: 'discuss-phase', labelKey: 'planningCommandBar.cmd.discussPhase.label', descKey: 'planningCommandBar.cmd.discussPhase.desc' },
      { name: 'plan-phase', labelKey: 'planningCommandBar.cmd.planPhase.label', descKey: 'planningCommandBar.cmd.planPhase.desc' },
    ],
  },
  {
    labelKey: 'planningCommandBar.groups.researchAnalysis',
    commands: [
      { name: 'survey', labelKey: 'planningCommandBar.cmd.survey.label', descKey: 'planningCommandBar.cmd.survey.desc' },
      { name: 'deep-dive', labelKey: 'planningCommandBar.cmd.deepDive.label', descKey: 'planningCommandBar.cmd.deepDive.desc' },
      { name: 'feasibility', labelKey: 'planningCommandBar.cmd.feasibility.label', descKey: 'planningCommandBar.cmd.feasibility.desc' },
      { name: 'assess-baseline', labelKey: 'planningCommandBar.cmd.assessBaseline.label', descKey: 'planningCommandBar.cmd.assessBaseline.desc' },
      { name: 'compare-methods', labelKey: 'planningCommandBar.cmd.compareMethods.label', descKey: 'planningCommandBar.cmd.compareMethods.desc' },
      { name: 'list-phase-assumptions', labelKey: 'planningCommandBar.cmd.listAssumptions.label', descKey: 'planningCommandBar.cmd.listAssumptions.desc' },
    ],
  },
  {
    labelKey: 'planningCommandBar.groups.requirements',
    commands: [
      { name: 'requirement', labelKey: 'planningCommandBar.cmd.requirement.label', descKey: 'planningCommandBar.cmd.requirement.desc' },
      { name: 'plan-milestone-gaps', labelKey: 'planningCommandBar.cmd.planGaps.label', descKey: 'planningCommandBar.cmd.planGaps.desc' },
      { name: 'complete-milestone', labelKey: 'planningCommandBar.cmd.completeMilestone.label', descKey: 'planningCommandBar.cmd.completeMilestone.desc' },
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
      <h3 class="command-bar-title">{{ t('planningCommandBar.title') }}</h3>
      <span v-if="grdInitStatus !== 'none'" class="init-status" :class="'init-' + grdInitStatus">
        {{ grdInitStatus }}
      </span>
    </div>

    <div v-for="group in commandGroups" :key="group.labelKey" class="command-group">
      <div class="group-label">{{ t(group.labelKey) }}</div>
      <div class="command-grid">
        <button
          v-for="cmd in group.commands"
          :key="cmd.name"
          class="command-btn"
          :disabled="isDisabled(status)"
          :title="t(cmd.descKey)"
          @click="handleClick(cmd.name)"
        >
          {{ t(cmd.labelKey) }}
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
