<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { GRD_COMMAND_MANIFEST } from './planningCommands';

const { t } = useI18n();

defineProps<{
  status: 'idle' | 'running' | 'waiting_input' | 'complete' | 'error';
  grdInitStatus: string;
}>();

const emit = defineEmits<{
  invoke: [command: string, args?: Record<string, string>];
  'build-loop': [];
}>();

// Single declarative source of truth — see planningCommands.ts.
const commandGroups = GRD_COMMAND_MANIFEST;

const isDisabled = (status: string) => status === 'running' || status === 'waiting_input';

function handleClick(commandName: string, group?: string) {
  emit('invoke', commandName, group ? { group } : undefined);
}
</script>

<template>
  <div class="command-bar">
    <div class="command-bar-header">
      <h3 class="command-bar-title">{{ t('planningCommandBar.title') }}</h3>
      <div class="command-bar-header-right">
        <button
          type="button"
          class="build-loop-btn"
          data-command="build-loop"
          :disabled="isDisabled(status)"
          :title="t('loopBuilder.subtitle')"
          @click="emit('build-loop')"
        >
          {{ t('planningCommandBar.buildLoop') }}
        </button>
        <span v-if="grdInitStatus !== 'none'" class="init-status" :class="'init-' + grdInitStatus">
          {{ grdInitStatus }}
        </span>
      </div>
    </div>

    <div v-for="group in commandGroups" :key="group.labelKey" class="command-group">
      <div class="group-label">{{ t(group.labelKey) }}</div>
      <div class="command-grid">
        <button
          v-for="cmd in group.commands"
          :key="cmd.name"
          class="command-btn"
          :class="{ 'is-deprecated': cmd.deprecated }"
          :disabled="isDisabled(status)"
          :title="t(cmd.descKey)"
          :data-command="cmd.name"
          :data-group="cmd.group"
          @click="handleClick(cmd.name, cmd.group)"
        >
          {{ t(cmd.labelKey) }}
          <span v-if="cmd.deprecated" class="deprecated-badge">{{
            t('planningCommandBar.deprecated')
          }}</span>
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

.command-bar-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.build-loop-btn {
  padding: 6px 12px;
  background: var(--accent-cyan-dim, rgba(0, 180, 216, 0.12));
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
  color: var(--accent-cyan);
  font-size: 0.78rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.build-loop-btn:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--accent-cyan);
}

.build-loop-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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

.command-btn.is-deprecated {
  opacity: 0.65;
}

.deprecated-badge {
  margin-left: 6px;
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 1px 4px;
  border-radius: 3px;
  color: var(--accent-amber, #ffb74d);
  background: rgba(255, 183, 77, 0.12);
}
</style>
