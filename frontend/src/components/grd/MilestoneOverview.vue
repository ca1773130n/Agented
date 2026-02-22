<script setup lang="ts">
import { computed } from 'vue';
import type { GrdMilestone, GrdPhase, GrdPlan } from '../../services/api';

const props = defineProps<{
  milestone: GrdMilestone | null;
  phases: GrdPhase[];
  plans: GrdPlan[];
}>();

const phasesCompleted = computed(() =>
  props.phases.filter((p) => p.status === 'completed').length
);

const totalPhases = computed(() => props.phases.length);

const plansByStatus = computed(() => {
  const counts: Record<string, number> = {
    pending: 0,
    in_progress: 0,
    in_review: 0,
    completed: 0,
    failed: 0,
  };
  for (const plan of props.plans) {
    if (plan.status in counts) {
      counts[plan.status]++;
    }
  }
  return counts;
});

const totalPlans = computed(() => props.plans.length);

const progressPercent = computed(() => {
  if (totalPlans.value === 0) return 0;
  return Math.round((plansByStatus.value.completed / totalPlans.value) * 100);
});

const statusPills = computed(() => [
  { label: 'Pending', count: plansByStatus.value.pending, cls: 'pill-pending' },
  { label: 'In Progress', count: plansByStatus.value.in_progress, cls: 'pill-in-progress' },
  { label: 'In Review', count: plansByStatus.value.in_review, cls: 'pill-in-review' },
  { label: 'Completed', count: plansByStatus.value.completed, cls: 'pill-completed' },
  { label: 'Failed', count: plansByStatus.value.failed, cls: 'pill-failed' },
]);
</script>

<template>
  <div v-if="milestone" class="milestone-overview">
    <div class="milestone-header">
      <div class="milestone-title-row">
        <h2 class="milestone-title">{{ milestone.title }}</h2>
        <span class="version-badge">{{ milestone.version }}</span>
      </div>
    </div>

    <div class="milestone-stats">
      <div class="stat-item">
        <span class="stat-label">Phases</span>
        <div class="stat-value-row">
          <span class="stat-value">{{ phasesCompleted }}/{{ totalPhases }}</span>
          <span class="stat-unit">complete</span>
        </div>
        <div class="mini-progress-bar">
          <div
            class="mini-progress-fill"
            :style="{ width: totalPhases > 0 ? (phasesCompleted / totalPhases * 100) + '%' : '0%' }"
          ></div>
        </div>
      </div>

      <div class="stat-divider"></div>

      <div class="stat-item">
        <span class="stat-label">Overall Progress</span>
        <div class="stat-value-row">
          <span class="stat-value stat-value-large">{{ progressPercent }}%</span>
        </div>
        <div class="mini-progress-bar">
          <div class="mini-progress-fill progress-cyan" :style="{ width: progressPercent + '%' }"></div>
        </div>
      </div>

      <div class="stat-divider"></div>

      <div class="stat-item stat-item-pills">
        <span class="stat-label">Plans by Status</span>
        <div class="status-pills">
          <span
            v-for="pill in statusPills"
            :key="pill.label"
            :class="['status-pill', pill.cls]"
            :title="pill.label"
          >
            <span class="pill-dot"></span>
            {{ pill.count }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.milestone-overview {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
}

.milestone-header {
  margin-bottom: 16px;
}

.milestone-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.milestone-title {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.version-badge {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
  padding: 3px 8px;
  border-radius: 4px;
}

.milestone-stats {
  display: flex;
  align-items: stretch;
  gap: 20px;
}

.stat-divider {
  width: 1px;
  background: var(--border-subtle);
  align-self: stretch;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 120px;
}

.stat-item-pills {
  flex: 1;
}

.stat-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value-row {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.stat-value {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.stat-value-large {
  font-size: 1.4rem;
}

.stat-unit {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.mini-progress-bar {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}

.mini-progress-fill {
  height: 100%;
  background: var(--accent-emerald);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.mini-progress-fill.progress-cyan {
  background: var(--accent-cyan);
}

.status-pills {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.8rem;
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

.pill-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.pill-pending .pill-dot {
  background: var(--text-muted);
}

.pill-in-progress .pill-dot {
  background: var(--accent-cyan);
}

.pill-in-review .pill-dot {
  background: var(--accent-purple, #a78bfa);
}

.pill-completed .pill-dot {
  background: var(--accent-green, var(--accent-emerald));
}

.pill-failed .pill-dot {
  background: var(--accent-red, crimson);
}
</style>
