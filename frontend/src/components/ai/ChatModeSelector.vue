<script setup lang="ts">
import type { ChatMode } from '../../composables/useAllMode';

defineProps<{ mode: ChatMode }>();
const emit = defineEmits<{ (e: 'update:mode', value: ChatMode): void }>();

const modes: Array<{ value: ChatMode; label: string; description: string }> = [
  { value: 'single', label: 'Single', description: 'Send to one backend' },
  { value: 'all', label: 'All', description: 'Send to all backends simultaneously' },
  { value: 'compound', label: 'Compound', description: 'All backends + AI synthesis' },
];
</script>

<template>
  <div class="chat-mode-selector">
    <button
      v-for="m in modes"
      :key="m.value"
      :class="['mode-btn', { active: mode === m.value }]"
      :title="m.description"
      @click="emit('update:mode', m.value)"
    >
      {{ m.label }}
    </button>
  </div>
</template>

<style scoped>
.chat-mode-selector {
  display: inline-flex;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  overflow: hidden;
}

.mode-btn {
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  border-right: 1px solid var(--border-default);
}

.mode-btn:last-child {
  border-right: none;
}

.mode-btn:hover:not(.active) {
  background: var(--bg-elevated, var(--bg-secondary));
  color: var(--text-primary);
}

.mode-btn.active {
  background: var(--accent-violet);
  color: #fff;
}
</style>
