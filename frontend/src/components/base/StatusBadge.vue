<script setup lang="ts">
defineProps<{
  label: string;
  variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'violet';
}>();
</script>

<template>
  <span :class="['ds-status-badge', 'ds-status-' + variant]">{{ label }}</span>
</template>

<style scoped>
.ds-status-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.6rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: capitalize;
}

.ds-status-success {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.ds-status-warning {
  background: var(--accent-amber-dim);
  color: var(--accent-amber);
}

.ds-status-danger {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.ds-status-info {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.ds-status-neutral {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-muted);
}

.ds-status-violet {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}
</style>
