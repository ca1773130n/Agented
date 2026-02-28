<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue';
import { VueDraggable, type DraggableEvent } from 'vue-draggable-plus';
import type { GrdPlan, GrdPhase } from '../../services/api';
import KanbanCard from './KanbanCard.vue';
import PhaseSwimLane from './PhaseSwimLane.vue';

const props = defineProps<{
  columnId: string;
  columnLabel: string;
  columnStatus: string;
  plans: GrdPlan[];
  phases: GrdPhase[];
  phaseLookup: Record<string, GrdPhase>;
}>();

const emit = defineEmits<{
  planMoved: [planId: string, newStatus: string];
  quickAdd: [title: string, status: string];
}>();

// Group-by-phase toggle
const groupByPhase = ref(false);

// Quick-add form state
const showQuickAdd = ref(false);
const quickAddTitle = ref('');
const quickAddInput = ref<HTMLInputElement | null>(null);

// Local reactive copy for VueDraggable v-model (flat mode)
const localPlans = ref<GrdPlan[]>([...props.plans]);

watch(() => props.plans, (newPlans) => {
  localPlans.value = [...newPlans];
}, { deep: true });

// Grouped plans by phase (for grouped mode)
const plansByPhase = computed(() => {
  const groups: { phase: GrdPhase; plans: GrdPlan[] }[] = [];
  const phaseMap = new Map<string, GrdPlan[]>();

  for (const plan of props.plans) {
    if (!phaseMap.has(plan.phase_id)) {
      phaseMap.set(plan.phase_id, []);
    }
    phaseMap.get(plan.phase_id)!.push(plan);
  }

  for (const [phaseId, phasePlans] of phaseMap) {
    const phase = props.phaseLookup[phaseId];
    if (phase) {
      groups.push({ phase, plans: phasePlans });
    }
  }

  groups.sort((a, b) => a.phase.phase_number - b.phase.phase_number);
  return groups;
});

// @add fires when an element is dropped into this column from another column
function onDragAdd(event: DraggableEvent<GrdPlan>) {
  if (event.data) {
    emit('planMoved', event.data.id, props.columnStatus);
  }
}

function onGroupedDragAdd(event: DraggableEvent<GrdPlan>) {
  if (event.data) {
    emit('planMoved', event.data.id, props.columnStatus);
  }
}

async function openQuickAdd() {
  showQuickAdd.value = true;
  quickAddTitle.value = '';
  await nextTick();
  quickAddInput.value?.focus();
}

function submitQuickAdd() {
  const title = quickAddTitle.value.trim();
  if (!title) {
    showQuickAdd.value = false;
    return;
  }
  emit('quickAdd', title, props.columnStatus);
  quickAddTitle.value = '';
  showQuickAdd.value = false;
}

function handleQuickAddKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    event.preventDefault();
    submitQuickAdd();
  } else if (event.key === 'Escape') {
    showQuickAdd.value = false;
  }
}
</script>

<template>
  <div class="kanban-column">
    <div class="kanban-column-header">
      <h3>{{ columnLabel }}</h3>
      <div class="column-header-right">
        <button
          v-if="plans.length > 0"
          class="group-toggle"
          :class="{ active: groupByPhase }"
          :title="groupByPhase ? 'Flat view' : 'Group by phase'"
          @click="groupByPhase = !groupByPhase"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
        </button>
        <span class="column-count">{{ plans.length }}</span>
      </div>
    </div>

    <!-- Flat mode (default): all cards in single VueDraggable -->
    <VueDraggable
      v-if="!groupByPhase"
      v-model="localPlans"
      group="kanban"
      :animation="200"
      ghost-class="kanban-ghost"
      drag-class="kanban-drag"
      class="kanban-column-body"
      @add="onDragAdd"
    >
      <KanbanCard
        v-for="plan in localPlans"
        :key="plan.id"
        :plan="plan"
        :phase-name="phaseLookup[plan.phase_id]?.name ?? 'Unknown'"
        :phase-number="phaseLookup[plan.phase_id]?.phase_number ?? 0"
      />
    </VueDraggable>

    <!-- Grouped mode: separate VueDraggable per phase swimlane -->
    <div v-else class="kanban-column-body kanban-column-grouped">
      <PhaseSwimLane
        v-for="group in plansByPhase"
        :key="group.phase.id"
        :phase-number="group.phase.phase_number"
        :phase-name="group.phase.name"
        :plan-count="group.plans.length"
      >
        <VueDraggable
          :model-value="group.plans"
          group="kanban"
          :animation="200"
          ghost-class="kanban-ghost"
          drag-class="kanban-drag"
          class="swimlane-draggable"
          @add="onGroupedDragAdd"
        >
          <KanbanCard
            v-for="plan in group.plans"
            :key="plan.id"
            :plan="plan"
            :phase-name="group.phase.name"
            :phase-number="group.phase.phase_number"
          />
        </VueDraggable>
      </PhaseSwimLane>
      <!-- Empty state for grouped mode when no plans -->
      <div v-if="plansByPhase.length === 0" class="column-empty">
        No plans
      </div>
    </div>

    <!-- Quick-add form / button -->
    <div class="kanban-column-footer">
      <div v-if="showQuickAdd" class="quick-add-form">
        <input
          ref="quickAddInput"
          v-model="quickAddTitle"
          class="quick-add-input"
          placeholder="Card title..."
          @keydown="handleQuickAddKeydown"
          @blur="submitQuickAdd"
        />
      </div>
      <button v-else class="quick-add-btn" @click="openQuickAdd">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        Add card
      </button>
    </div>
  </div>
</template>

<style scoped>
.kanban-column {
  flex: 1;
  min-width: 260px;
  max-width: 340px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
}

.kanban-column-header {
  padding: 16px;
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.kanban-column-header h3 {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0;
}

.column-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.group-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.group-toggle:hover {
  color: var(--text-secondary);
  background: var(--bg-tertiary);
}

.group-toggle.active {
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
}

.group-toggle svg {
  width: 14px;
  height: 14px;
}

.column-count {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 4px;
}

.kanban-column-body {
  flex: 1;
  padding: 12px;
  min-height: 100px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kanban-column-grouped {
  gap: 4px;
}

.swimlane-draggable {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 32px;
}

.column-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 12px;
  color: var(--text-tertiary);
  font-size: 0.8rem;
}

/* Quick-add footer */
.kanban-column-footer {
  padding: 8px 12px 12px;
}

.quick-add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 12px;
  border: 1px dashed var(--border-subtle);
  border-radius: 8px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
}

.quick-add-btn:hover {
  color: var(--text-secondary);
  border-color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
}

.quick-add-form {
  display: flex;
}

.quick-add-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--accent-cyan);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 0.8rem;
  font-family: inherit;
  outline: none;
}
</style>

<style>
/* Global (unscoped) ghost and drag classes for SortableJS */
.kanban-ghost {
  opacity: 0.4;
  background: var(--accent-cyan-dim) !important;
  border: 2px dashed var(--accent-cyan) !important;
  border-radius: 8px;
}

.kanban-drag {
  box-shadow: var(--shadow-lg) !important;
  transform: rotate(2deg);
}
</style>
