<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
}>();
</script>

<template>
  <div class="ds-empty-state">
    <div class="ds-empty-icon">
      <slot name="icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10" />
          <path d="M8 12h8" />
        </svg>
      </slot>
    </div>
    <h3>{{ title }}</h3>
    <p v-if="description" class="ds-empty-description">{{ description }}</p>
    <div v-if="$slots.actions" class="ds-empty-state-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.ds-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 3rem 1.5rem;
  color: var(--text-muted);
}

.ds-empty-icon {
  margin-bottom: 1rem;
  opacity: 0.5;
}

.ds-empty-icon svg {
  width: 48px;
  height: 48px;
}

.ds-empty-state h3 {
  font-size: 1.1rem;
  color: var(--text-primary);
  margin: 0 0 0.5rem 0;
}

.ds-empty-description {
  color: var(--text-secondary);
  margin: 0 0 1rem 0;
}

.ds-empty-state-actions {
  margin-top: 0.5rem;
}
</style>
