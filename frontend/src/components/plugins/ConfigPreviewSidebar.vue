<script setup lang="ts">
defineProps<{
  /** Whether config has been detected */
  hasConfig: boolean;
  /** SVG path(s) for the empty-state icon */
  emptyIconPaths: string[];
  /** Empty-state description text */
  emptyText: string;
  /** Sidebar title (default: "Config Preview") */
  title?: string;
}>();
</script>

<template>
  <div class="sidebar-right">
    <div class="sidebar-header">
      <h3>{{ title || 'Config Preview' }}</h3>
    </div>
    <div v-if="!hasConfig" class="sidebar-empty">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path v-for="(d, i) in emptyIconPaths" :key="i" :d="d"/>
      </svg>
      <p>{{ emptyText }}</p>
    </div>
    <div v-else class="config-preview">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.sidebar-right {
  width: 300px;
  flex-shrink: 0;
  border-left: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--bg-secondary);
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--border-default);
}

.sidebar-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.sidebar-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  text-align: center;
  color: var(--text-tertiary);
}

.sidebar-empty svg {
  width: 40px;
  height: 40px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.sidebar-empty p {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
}

.config-preview {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
