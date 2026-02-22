<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    message?: string;
  }>(),
  {
    title: 'Something went wrong',
  },
);

defineEmits<{
  (e: 'retry'): void;
}>();
</script>

<template>
  <div class="ds-error-state" role="alert">
    <div class="ds-error-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 8v4M12 16h.01" />
      </svg>
    </div>
    <h3>{{ title }}</h3>
    <p v-if="message" class="ds-error-message">{{ message }}</p>
    <button class="btn btn-primary" @click="$emit('retry')">Retry</button>
  </div>
</template>

<style scoped>
.ds-error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 3rem 1.5rem;
}

.ds-error-icon {
  margin-bottom: 1rem;
  color: var(--accent-crimson, #ff4081);
}

.ds-error-icon svg {
  width: 48px;
  height: 48px;
}

.ds-error-state h3 {
  font-size: 1.1rem;
  color: var(--text-primary);
  margin: 0 0 0.5rem 0;
}

.ds-error-message {
  color: var(--text-secondary);
  margin: 0 0 1rem 0;
}
</style>
