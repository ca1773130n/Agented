<script setup lang="ts">
defineProps<{
  label: string;
  errorKeys?: string[];
  errors?: Record<string, string | null>;
  errorTitle?: string;
}>();

const emit = defineEmits<{
  retry: [key: string];
}>();

function hasAnyError(errs: Record<string, string | null> | undefined, keys: string[] | undefined): boolean {
  if (!errs || !keys || keys.length === 0) return false;
  return keys.some(k => !!errs[k]);
}

function defaultTitle(errs: Record<string, string | null> | undefined, keys: string[] | undefined): string {
  if (!errs || !keys) return '';
  const named = keys.filter(k => !!errs[k]);
  if (named.length === 1) return errs[named[0]] || '';
  return named.map(k => k.charAt(0).toUpperCase() + k.slice(1)).join(', ') + ' failed to load';
}

function onRetry(key: string) {
  emit('retry', key);
}

defineExpose({ hasAnyError, defaultTitle, onRetry });
</script>

<template>
  <div class="nav-section-label">
    {{ label }}
    <span
      v-if="hasAnyError(errors, errorKeys)"
      class="section-error-badge"
      :title="errorTitle || defaultTitle(errors, errorKeys)"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <template v-for="key in errorKeys" :key="key">
        <button
          v-if="errors && errors[key]"
          class="section-retry-btn"
          @click.stop="onRetry(key)"
        >Retry</button>
      </template>
    </span>
  </div>
</template>

<style scoped>
.section-error-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 4px;
  color: var(--accent-amber);
  vertical-align: middle;
}

.section-error-badge svg {
  flex-shrink: 0;
}

.section-retry-btn {
  font-size: 0.6rem;
  font-weight: 600;
  color: var(--accent-cyan);
  background: none;
  border: 1px solid var(--accent-cyan);
  border-radius: 3px;
  padding: 1px 4px;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  transition: background var(--transition-fast);
}

.section-retry-btn:hover {
  background: rgba(0, 212, 255, 0.1);
}
</style>
