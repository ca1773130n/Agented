<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

withDefaults(
  defineProps<{
    fallbackTitle?: string;
  }>(),
  {
    fallbackTitle: '',
  },
);

const hasError = ref(false);
const errorMessage = ref('');
const recoveryKey = ref(0);

onErrorCaptured((err: Error, _instance, info: string) => {
  hasError.value = true;
  errorMessage.value = `${err.message} (in ${info})`;
  // Returning false stops propagation to the global errorHandler, which is the
  // only path into the system-error capture API — so report from here too,
  // otherwise the original error is invisible to error capture / autofix and
  // only downstream artifacts (e.g. corrupted-patch crashes) get recorded.
  try {
    import('../../services/api/system').then(({ systemErrorApi }) => {
      systemErrorApi.reportError({
        source: 'frontend',
        category: 'frontend_error',
        message: err instanceof Error ? err.message : String(err),
        stack_trace: err instanceof Error ? err.stack : undefined,
        context_json: JSON.stringify({ component: info, boundary: 'ErrorBoundary', url: window.location.href }),
      }).catch(() => {});
    }).catch(() => {});
  } catch { /* reporting is best-effort */ }
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
    <h3 class="error-boundary-title">{{ fallbackTitle || t('errorBoundary.title') }}</h3>
    <p class="error-boundary-message">{{ errorMessage }}</p>
    <button class="btn btn-primary" @click="recover">{{ t('errorBoundary.tryAgain') }}</button>
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
