<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue';

withDefaults(
  defineProps<{
    fallbackTitle?: string;
  }>(),
  {
    fallbackTitle: 'Something went wrong',
  },
);

const hasError = ref(false);
const errorMessage = ref('');
const recoveryKey = ref(0);

onErrorCaptured((err: Error, _instance, info: string) => {
  hasError.value = true;
  errorMessage.value = `${err.message} (in ${info})`;
  return false;
});

function recover() {
  hasError.value = false;
  errorMessage.value = '';
  recoveryKey.value++;
}
</script>

<template>
  <div v-if="hasError" class="error-boundary-fallback" role="alert">
    <div class="error-boundary-icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 8v4M12 16h.01" />
      </svg>
    </div>
    <h3 class="error-boundary-title">{{ fallbackTitle }}</h3>
    <p class="error-boundary-message">{{ errorMessage }}</p>
    <button class="btn btn-primary" @click="recover">Try Again</button>
  </div>
  <div v-else :key="recoveryKey">
    <slot />
  </div>
</template>

<style scoped>
.error-boundary-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 3rem 1.5rem;
}

.error-boundary-icon {
  margin-bottom: 1rem;
  color: var(--accent-crimson, #ff4081);
}

.error-boundary-icon svg {
  width: 48px;
  height: 48px;
}

.error-boundary-title {
  font-size: 1.1rem;
  color: var(--text-primary);
  margin: 0 0 0.5rem 0;
}

.error-boundary-message {
  color: var(--text-secondary);
  margin: 0 0 1rem 0;
  max-width: 500px;
  word-break: break-word;
}
</style>
