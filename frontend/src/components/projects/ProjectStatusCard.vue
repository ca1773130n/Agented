<script setup lang="ts">
import type { Project } from '../../services/api';

defineProps<{
  project: Project;
}>();

const emit = defineEmits<{
  (e: 'navigateToProductDashboard', productId: string): void;
}>();

function getStatusClass(status: string): string {
  switch (status) {
    case 'active': return 'status-active';
    case 'archived': return 'status-archived';
    case 'planning': return 'status-planning';
    default: return '';
  }
}
</script>

<template>
  <div class="status-card">
    <div class="status-card-header">
      <div class="project-icon-lg">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
      </div>
      <div class="status-info">
        <h2>{{ project.name }}</h2>
        <div class="status-meta">
          <span class="meta-pill" :class="getStatusClass(project.status)">
            {{ project.status }}
          </span>
          <span
            v-if="project.product_name"
            class="meta-pill product"
            :class="{ 'entity-link': project.product_id }"
            @click="project.product_id && emit('navigateToProductDashboard', project.product_id)"
          >
            {{ project.product_name }}
          </span>
        </div>
      </div>
    </div>
    <p v-if="project.description" class="project-description">{{ project.description }}</p>
  </div>
</template>

<style scoped>
.status-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 28px;
}

.status-card-header {
  display: flex;
  align-items: center;
  gap: 20px;
}

.project-icon-lg {
  width: 56px;
  height: 56px;
  background: linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan));
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.project-icon-lg svg {
  width: 28px;
  height: 28px;
  color: var(--bg-primary);
}

.status-info h2 {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}

.status-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.meta-pill.status-active {
  background: rgba(0, 255, 136, 0.2);
  color: #00ff88;
}

.meta-pill.status-archived {
  background: rgba(136, 136, 136, 0.2);
  color: #888;
}

.meta-pill.status-planning {
  background: rgba(136, 85, 255, 0.2);
  color: #8855ff;
}

.meta-pill.product {
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15));
  color: var(--accent-cyan, #00d4ff);
}

.project-description {
  margin-top: 16px;
  color: var(--text-secondary);
  line-height: 1.6;
}
</style>
