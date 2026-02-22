<script setup lang="ts">
defineProps<{
  modelValue: 'form' | 'chat';
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: 'form' | 'chat'): void;
}>();
</script>

<template>
  <div class="mode-tabs">
    <button
      class="mode-tab"
      :class="{ active: modelValue === 'form' }"
      @click="emit('update:modelValue', 'form')"
    >Form</button>
    <button
      class="mode-tab"
      :class="{ active: modelValue === 'chat' }"
      @click="emit('update:modelValue', 'chat')"
    >AI Chat</button>
  </div>
</template>

<style scoped>
.mode-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 4px;
}

.mode-tab {
  padding: 6px 16px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.mode-tab.active {
  background: var(--accent-violet);
  color: #fff;
}

.mode-tab:hover:not(.active) {
  color: var(--text-primary);
}
</style>
