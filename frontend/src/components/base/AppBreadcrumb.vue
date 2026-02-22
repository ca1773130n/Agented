<script setup lang="ts">
defineProps<{
  items: Array<{ label: string; action?: () => void }>
}>();
</script>

<template>
  <nav class="app-breadcrumb">
    <template v-for="(item, i) in items" :key="i">
      <a v-if="item.action" href="#" @click.prevent="item.action">{{ item.label }}</a>
      <span v-else class="current">{{ item.label }}</span>
      <span v-if="i < items.length - 1" class="sep">/</span>
    </template>
  </nav>
</template>

<style scoped>
.app-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  margin-bottom: 24px;
}

.app-breadcrumb a {
  color: var(--text-tertiary);
  text-decoration: none;
  transition: color var(--transition-fast);
}

.app-breadcrumb a:hover {
  color: var(--accent-cyan);
}

.sep {
  color: var(--text-muted);
}

.current {
  color: var(--text-primary);
  font-weight: 500;
}
</style>
