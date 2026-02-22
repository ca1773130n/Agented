<script setup lang="ts">
import type { GrdPlan } from '../../services/api';

defineProps<{
  plan: GrdPlan;
  phaseName: string;
  phaseNumber: number;
  agentName?: string;
}>();

function statusLabel(status: string): string {
  switch (status) {
    case 'pending': return 'Pending';
    case 'in_progress': return 'In Progress';
    case 'in_review': return 'In Review';
    case 'completed': return 'Completed';
    case 'failed': return 'Failed';
    default: return status;
  }
}

function statusClass(status: string): string {
  switch (status) {
    case 'pending': return 'status-pending';
    case 'in_progress': return 'status-in-progress';
    case 'in_review': return 'status-in-review';
    case 'completed': return 'status-completed';
    case 'failed': return 'status-failed';
    default: return 'status-pending';
  }
}
</script>

<template>
  <div class="kanban-card">
    <div class="card-header">
      <span class="card-title">{{ plan.title }}</span>
      <span class="card-number">#{{ String(plan.plan_number).padStart(2, '0') }}</span>
    </div>
    <div class="card-meta">
      <span class="phase-indicator">Phase {{ phaseNumber }}: {{ phaseName }}</span>
    </div>
    <div class="card-footer">
      <span :class="['status-badge', statusClass(plan.status)]">{{ statusLabel(plan.status) }}</span>
      <span class="agent-name">{{ agentName || 'Unassigned' }}</span>
    </div>
  </div>
</template>

<style scoped>
.kanban-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 12px;
  cursor: grab;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kanban-card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-sm);
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.card-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
  flex: 1;
  min-width: 0;
}

.card-number {
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.phase-indicator {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 500;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.status-pending {
  background: var(--text-muted);
  color: var(--text-primary);
}

.status-in-progress {
  background: var(--accent-cyan);
  color: var(--text-on-accent);
}

.status-in-review {
  background: var(--accent-purple, #a78bfa);
  color: var(--text-on-accent);
}

.status-completed {
  background: var(--accent-green, var(--accent-emerald));
  color: var(--text-on-accent);
}

.status-failed {
  background: var(--accent-red, crimson);
  color: #fff;
}

.agent-name {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
