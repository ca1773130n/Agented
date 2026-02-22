<script setup lang="ts">
withDefaults(
  defineProps<{
    message?: string;
  }>(),
  {
    message: 'Loading...',
  },
);
</script>

<template>
  <div class="ds-loading-state" role="status" aria-live="polite">
    <div class="ds-spinner"></div>
    <span class="ds-loading-message">{{ message }}</span>
  </div>
</template>

<style scoped>
.ds-loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 3rem 1.5rem;
}

.ds-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--bg-tertiary, #1a1a24);
  border-top-color: var(--accent-color, var(--accent-cyan, #00d4ff));
  border-radius: 50%;
  animation: ds-spin 0.8s linear infinite;
  margin-bottom: 1rem;
}

.ds-loading-message {
  color: var(--text-secondary);
  font-size: 0.9rem;
}

@keyframes ds-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
