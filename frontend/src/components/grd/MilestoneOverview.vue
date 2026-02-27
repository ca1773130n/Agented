<script setup lang="ts">
import { computed, ref, nextTick } from 'vue';
import type { GrdMilestone, GrdPhase, GrdPlan } from '../../services/api';

const props = defineProps<{
  milestone: GrdMilestone | null;
  phases: GrdPhase[];
  plans: GrdPlan[];
}>();

const emit = defineEmits<{
  createPhase: [name: string, goal: string];
  phaseCommand: [phaseNumber: number, command: string];
}>();

// New phase form
const showNewPhaseForm = ref(false);
const newPhaseName = ref('');
const newPhaseGoal = ref('');
const newPhaseInput = ref<HTMLInputElement | null>(null);

async function openNewPhaseForm() {
  showNewPhaseForm.value = true;
  newPhaseName.value = '';
  newPhaseGoal.value = '';
  await nextTick();
  newPhaseInput.value?.focus();
}

function submitNewPhase() {
  const name = newPhaseName.value.trim();
  if (!name) {
    showNewPhaseForm.value = false;
    return;
  }
  emit('createPhase', name, newPhaseGoal.value.trim());
  showNewPhaseForm.value = false;
  newPhaseName.value = '';
  newPhaseGoal.value = '';
}

function handlePhaseKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    event.preventDefault();
    submitNewPhase();
  } else if (event.key === 'Escape') {
    showNewPhaseForm.value = false;
  }
}

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

      <div class="stat-divider"></div>

      <div class="stat-item stat-item-action">
        <template v-if="!showNewPhaseForm">
          <button class="new-phase-btn" @click="openNewPhaseForm">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Phase
          </button>
        </template>
        <template v-else>
          <div class="new-phase-form">
            <input
              ref="newPhaseInput"
              v-model="newPhaseName"
              class="new-phase-input"
              placeholder="Phase name..."
              @keydown="handlePhaseKeydown"
            />
            <input
              v-model="newPhaseGoal"
              class="new-phase-input"
              placeholder="Goal (optional)"
              @keydown="handlePhaseKeydown"
            />
            <div class="new-phase-actions">
              <button class="new-phase-submit" @click="submitNewPhase">Create</button>
              <button class="new-phase-cancel" @click="showNewPhaseForm = false">Cancel</button>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Phase cards with action buttons -->
    <div v-if="phases.length > 0" class="phase-cards">
      <div
        v-for="phase in phases"
        :key="phase.id"
        class="phase-card"
      >
        <div class="phase-card-main">
          <span class="phase-number">{{ String(phase.phase_number).padStart(2, '0') }}</span>
          <span class="phase-name">{{ phase.name }}</span>
          <span class="phase-status-badge" :class="'phase-' + phase.status">{{ phase.status }}</span>
          <span v-if="phase.plan_count > 0" class="phase-plan-count">{{ phase.plan_count }} plans</span>
        </div>
        <div class="phase-actions">
          <button
            class="phase-action-btn"
            title="Discuss this phase"
            @click="emit('phaseCommand', phase.phase_number, 'discuss-phase')"
          >Discuss</button>
          <button
            class="phase-action-btn"
            title="Plan this phase"
            @click="emit('phaseCommand', phase.phase_number, 'plan-phase')"
          >Plan</button>
          <button
            class="phase-action-btn"
            title="Research this phase"
            @click="emit('phaseCommand', phase.phase_number, 'survey')"
          >Research</button>
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

.stat-item-action {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 120px;
}

.new-phase-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: 1px dashed var(--border-subtle);
  border-radius: 8px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.new-phase-btn:hover {
  color: var(--text-secondary);
  border-color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
}

.new-phase-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 200px;
}

.new-phase-input {
  padding: 6px 10px;
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 0.8rem;
  font-family: inherit;
  outline: none;
}

.new-phase-actions {
  display: flex;
  gap: 6px;
}

.new-phase-submit {
  padding: 4px 12px;
  border: none;
  border-radius: 6px;
  background: var(--accent-cyan);
  color: var(--bg-primary);
  font-size: 0.75rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
}

.new-phase-submit:hover {
  opacity: 0.9;
}

.new-phase-cancel {
  padding: 4px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 0.75rem;
  font-family: inherit;
  cursor: pointer;
}

.new-phase-cancel:hover {
  color: var(--text-secondary);
}

/* Phase cards */
.phase-cards {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 16px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 16px;
}

.phase-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--bg-tertiary);
  transition: background 0.15s ease;
}

.phase-card:hover {
  background: var(--bg-elevated, var(--bg-tertiary));
}

.phase-card-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.phase-number {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.phase-name {
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.phase-status-badge {
  font-size: 0.65rem;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  flex-shrink: 0;
}

.phase-pending {
  color: var(--text-muted);
  background: rgba(128, 128, 128, 0.1);
}

.phase-active {
  color: var(--accent-cyan);
  background: rgba(0, 180, 216, 0.1);
}

.phase-completed {
  color: var(--accent-emerald);
  background: rgba(0, 255, 136, 0.1);
}

.phase-skipped {
  color: var(--text-tertiary);
  background: rgba(128, 128, 128, 0.08);
}

.phase-plan-count {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.phase-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}

.phase-card:hover .phase-actions {
  opacity: 1;
}

.phase-action-btn {
  padding: 3px 8px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-tertiary);
  font-size: 0.68rem;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.phase-action-btn:hover {
  color: var(--text-primary);
  border-color: var(--accent-cyan);
  background: var(--accent-cyan-dim, rgba(0, 180, 216, 0.08));
}
</style>
