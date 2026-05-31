<script setup lang="ts">
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

defineProps<{
  sessionStatus: string | null;
  isStreaming: boolean;
}>();

const emit = defineEmits<{
  (e: 'start'): void;
  (e: 'pause'): void;
  (e: 'resume'): void;
  (e: 'stop'): void;
}>();
</script>

<template>
  <div class="session-controls">
    <!-- New Session is ALWAYS available. Previously this was gated
         on the active session being completed/failed/absent, which
         meant clicking a still-active prior session in the History
         sidebar hid the button entirely — no way to start a new chat
         without first stopping the selected one. v0.7.59. -->
    <button
      class="ctrl-btn ctrl-btn--start"
      :title="t('sessionControls.newSession')"
      @click="emit('start')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19" />
        <line x1="5" y1="12" x2="19" y2="12" />
      </svg>
      <span>{{ t('sessionControls.newSession') }}</span>
    </button>

    <!-- Active: show Pause + Stop alongside New Session -->
    <template v-if="sessionStatus === 'active'">
      <button
        class="ctrl-btn ctrl-btn--pause"
        :title="t('sessionControls.pauseSession')"
        @click="emit('pause')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="6" y="4" width="4" height="16" rx="1" />
          <rect x="14" y="4" width="4" height="16" rx="1" />
        </svg>
        <span>{{ t('sessionControls.pause') }}</span>
      </button>
      <button
        class="ctrl-btn ctrl-btn--stop"
        :title="t('sessionControls.stopSession')"
        @click="emit('stop')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
        <span>{{ t('sessionControls.stop') }}</span>
      </button>
    </template>

    <!-- Paused: show Resume + Stop alongside New Session -->
    <template v-if="sessionStatus === 'paused'">
      <button
        class="ctrl-btn ctrl-btn--resume"
        :title="t('sessionControls.resumeSession')"
        @click="emit('resume')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="5,3 19,12 5,21" />
        </svg>
        <span>{{ t('sessionControls.resume') }}</span>
      </button>
      <button
        class="ctrl-btn ctrl-btn--stop"
        :title="t('sessionControls.stopSession')"
        @click="emit('stop')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
        <span>{{ t('sessionControls.stop') }}</span>
      </button>
    </template>
  </div>
</template>

<style scoped>
.session-controls {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ctrl-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border: 1px solid var(--border-default);
  border-radius: 16px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.ctrl-btn:hover {
  border-color: var(--border-subtle);
  color: var(--text-primary);
}

.ctrl-btn svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.ctrl-btn--start:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.ctrl-btn--pause:hover {
  border-color: var(--accent-yellow);
  color: var(--accent-yellow);
}

.ctrl-btn--resume:hover {
  border-color: var(--accent-green);
  color: var(--accent-green);
}

.ctrl-btn--stop:hover {
  border-color: var(--accent-red);
  color: var(--accent-red);
}
</style>
