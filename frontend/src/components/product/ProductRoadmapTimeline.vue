<script setup lang="ts">
import { computed } from 'vue';
import type { ProductMilestone } from '../../services/api';

const props = defineProps<{
  milestones: ProductMilestone[];
}>();

const sortedMilestones = computed(() =>
  [...props.milestones].sort((a, b) => a.sort_order - b.sort_order)
);

function formatDate(dateStr?: string): string {
  if (!dateStr) return 'No date';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

function getStatusColor(status: string): { bg: string; border: string } {
  switch (status) {
    case 'planned':
      return { bg: 'rgba(136, 85, 255, 0.3)', border: '#8855ff' };
    case 'in_progress':
      return { bg: 'rgba(0, 212, 255, 0.3)', border: '#00d4ff' };
    case 'completed':
      return { bg: 'rgba(0, 255, 136, 0.3)', border: '#00ff88' };
    case 'cancelled':
      return { bg: 'rgba(128, 128, 128, 0.3)', border: '#888' };
    default:
      return { bg: 'rgba(136, 85, 255, 0.3)', border: '#8855ff' };
  }
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <div class="header-left">
        <h3>Roadmap Timeline</h3>
        <span class="card-count">{{ milestones.length }} milestones</span>
      </div>
    </div>

    <div v-if="sortedMilestones.length === 0" class="empty-state">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
          <line x1="4" y1="22" x2="4" y2="15"/>
        </svg>
      </div>
      <p>No milestones defined</p>
    </div>

    <div v-else class="timeline-grid">
      <div
        v-for="ms in sortedMilestones"
        :key="ms.id"
        class="timeline-row"
      >
        <div class="timeline-date">{{ formatDate(ms.target_date) }}</div>
        <div class="timeline-bar-container">
          <div
            class="timeline-bar"
            :style="{
              width: Math.max(ms.progress_pct, 5) + '%',
              background: getStatusColor(ms.status).bg,
              borderLeft: '3px solid ' + getStatusColor(ms.status).border,
            }"
          >
            <span class="bar-label">
              {{ ms.title }} <span class="bar-version">{{ ms.version }}</span>
            </span>
            <span class="bar-pct" :style="{ color: getStatusColor(ms.status).border }">{{ ms.progress_pct }}%</span>
          </div>
        </div>
      </div>
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

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
}

.empty-icon {
  width: 48px;
  height: 48px;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.empty-icon svg {
  width: 100%;
  height: 100%;
}

.empty-state p {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.timeline-grid {
  display: flex;
  flex-direction: column;
  padding: 16px 20px;
  gap: 12px;
}

.timeline-row {
  display: grid;
  grid-template-columns: 120px 1fr;
  align-items: center;
  gap: 12px;
}

.timeline-date {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  text-align: right;
  white-space: nowrap;
}

.timeline-bar-container {
  position: relative;
  height: 36px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  overflow: hidden;
}

.timeline-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
  padding: 0 12px;
  border-radius: 6px;
  min-width: 80px;
  transition: width 0.4s ease;
}

.bar-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-version {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  margin-left: 6px;
}

.bar-pct {
  font-size: 0.7rem;
  font-weight: 700;
  font-family: var(--font-mono);
  flex-shrink: 0;
  margin-left: 8px;
}
</style>
