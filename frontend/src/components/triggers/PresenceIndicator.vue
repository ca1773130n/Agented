<script setup lang="ts">
import type { ViewerInfo } from '../../services/api';

defineProps<{
  viewers: ViewerInfo[];
}>();

function getInitial(name: string): string {
  return name.charAt(0).toUpperCase();
}

function getColor(viewerId: string): string {
  // Deterministic color from viewer ID
  const colors = [
    '#00d4ff', '#8b5cf6', '#10b981', '#f59e0b',
    '#ef4444', '#ec4899', '#6366f1', '#14b8a6',
  ];
  let hash = 0;
  for (let i = 0; i < viewerId.length; i++) {
    hash = ((hash << 5) - hash) + viewerId.charCodeAt(i);
    hash |= 0;
  }
  return colors[Math.abs(hash) % colors.length];
}
</script>

<template>
  <div v-if="viewers.length > 0" class="presence-indicator">
    <div class="viewer-badges">
      <TransitionGroup name="viewer">
        <span
          v-for="viewer in viewers"
          :key="viewer.viewer_id"
          class="viewer-badge"
          :style="{ '--badge-color': getColor(viewer.viewer_id) }"
          :title="viewer.name"
        >
          {{ getInitial(viewer.name) }}
        </span>
      </TransitionGroup>
    </div>
    <span class="viewer-count">{{ viewers.length }} watching</span>
  </div>
</template>

<style scoped>
.presence-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.viewer-badges {
  display: flex;
  gap: -4px;
}

.viewer-badge {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--bg-primary, #0a0a0a);
  background: var(--badge-color, var(--accent-cyan));
  border: 2px solid var(--bg-secondary, #141414);
  margin-left: -4px;
  cursor: default;
  transition: transform 0.15s ease;
}

.viewer-badge:first-child {
  margin-left: 0;
}

.viewer-badge:hover {
  transform: scale(1.15);
  z-index: 1;
}

.viewer-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

/* TransitionGroup animations */
.viewer-enter-active {
  transition: all 0.3s ease;
}

.viewer-leave-active {
  transition: all 0.2s ease;
}

.viewer-enter-from {
  opacity: 0;
  transform: scale(0.5);
}

.viewer-leave-to {
  opacity: 0;
  transform: scale(0.5);
}
</style>
