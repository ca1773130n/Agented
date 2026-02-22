<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
  gradient?: string;
}>();
</script>

<template>
  <div class="ds-page-header">
    <div class="ds-header-content">
      <h1 :class="gradient ? 'gradient-' + gradient : ''">{{ title }}</h1>
      <p v-if="subtitle" class="ds-subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="ds-header-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<style scoped>
.ds-page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
  gap: 1rem;
  flex-wrap: wrap;
}

.ds-header-content h1 {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.ds-subtitle {
  color: var(--text-secondary);
  margin: 0;
}

.ds-header-actions {
  display: flex;
  gap: 12px;
}
</style>
