<script setup lang="ts">
import type { ProductHealth } from '../../services/api';

defineProps<{
  health: ProductHealth;
  projects: Array<{ id: string; name: string; status: string }>;
}>();

const emit = defineEmits<{
  (e: 'navigateToProject', projectId: string): void;
}>();

function getHealthIcon(health: string): string {
  switch (health) {
    case 'green': return 'circle';
    case 'yellow': return 'triangle';
    case 'red': return 'diamond';
    default: return 'circle';
  }
}

function getHealthColor(health: string): string {
  switch (health) {
    case 'green': return '#00ff88';
    case 'yellow': return '#ffbb00';
    case 'red': return '#ff4081';
    default: return '#888';
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'active': return '#00ff88';
    case 'archived': return '#888';
    case 'planning': return '#8855ff';
    default: return '#888';
  }
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <div class="header-left">
        <h3>Project Health</h3>
        <span class="card-count">{{ health.project_count }} projects</span>
      </div>
    </div>

    <!-- Health Summary -->
    <div class="health-summary">
      <div class="health-badge" :style="{ background: getHealthColor(health.health) + '20' }">
        <svg v-if="getHealthIcon(health.health) === 'circle'" viewBox="0 0 24 24" fill="none" :stroke="getHealthColor(health.health)" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
        </svg>
        <svg v-else-if="getHealthIcon(health.health) === 'triangle'" viewBox="0 0 24 24" fill="none" :stroke="getHealthColor(health.health)" stroke-width="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" :stroke="getHealthColor(health.health)" stroke-width="2">
          <rect x="4.93" y="4.93" width="14.14" height="14.14" rx="2" transform="rotate(45 12 12)"/>
        </svg>
      </div>
      <div class="health-info">
        <span class="health-label" :style="{ color: getHealthColor(health.health) }">
          {{ health.health.toUpperCase() }}
        </span>
        <span class="health-reason">{{ health.reason }}</span>
        <span class="health-counts">{{ health.active_count }} active / {{ health.project_count }} total</span>
      </div>
    </div>

    <!-- Project Cards Grid -->
    <div v-if="projects.length > 0" class="projects-grid">
      <div
        v-for="proj in projects"
        :key="proj.id"
        class="project-card"
        @click="emit('navigateToProject', proj.id)"
      >
        <span class="project-name">{{ proj.name }}</span>
        <div class="project-status">
          <span class="status-dot" :style="{ background: getStatusColor(proj.status) }"></span>
          <span class="status-text">{{ proj.status }}</span>
        </div>
      </div>
    </div>
    <div v-else class="empty-state">
      <p>No projects assigned</p>
    </div>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 4px 8px;
  border-radius: 4px;
}

.health-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.health-badge {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.health-badge svg {
  width: 24px;
  height: 24px;
}

.health-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.health-label {
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  font-family: var(--font-mono);
}

.health-reason {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.health-counts {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  padding: 20px;
}

.project-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  background: var(--bg-tertiary);
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.project-card:hover {
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.05);
}

.project-name {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-status {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-text {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-tertiary);
  letter-spacing: 0.03em;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}

.empty-state p {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}
</style>
