<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { GrdPlan, GrdPhase } from '../../services/api';
import KanbanColumn from './KanbanColumn.vue';

const props = defineProps<{
  projectId: string;
  milestoneId: string | null;
  phases: GrdPhase[];
  plans: GrdPlan[];
}>();

const emit = defineEmits<{
  planStatusChanged: [planId: string, newStatus: string];
  quickAdd: [title: string, status: string];
}>();

// Column configuration
const COLUMNS = [
  { id: 'backlog', label: 'Backlog', status: 'pending', phaseFilter: 'pending' },
  { id: 'planned', label: 'Planned', status: 'pending', phaseFilter: 'active' },
  { id: 'in-progress', label: 'In Progress', status: 'in_progress', phaseFilter: null },
  { id: 'in-review', label: 'In Review', status: 'in_review', phaseFilter: null },
  { id: 'done', label: 'Done', status: 'completed', phaseFilter: null },
] as const;

// Local reactive copy to avoid mutating props
const localPlans = ref<GrdPlan[]>([...props.plans]);

watch(() => props.plans, (newPlans) => {
  localPlans.value = [...newPlans];
}, { deep: true });

// Map phase IDs to their status
const phaseStatusMap = computed(() => {
  const map: Record<string, string> = {};
  for (const phase of props.phases) {
    map[phase.id] = phase.status;
  }
  return map;
});

// Phase lookup for card display
const phaseLookup = computed(() => {
  const lookup: Record<string, GrdPhase> = {};
  for (const phase of props.phases) {
    lookup[phase.id] = phase;
  }
  return lookup;
});

// Filter plans per column
const columnPlans = computed(() => {
  const result: Record<string, GrdPlan[]> = {};
  const psMap = phaseStatusMap.value;

  for (const col of COLUMNS) {
    if (col.id === 'backlog') {
      // Backlog: failed plans OR pending plans in non-active phases
      result[col.id] = localPlans.value.filter(
        (p) => p.status === 'failed' || (p.status === 'pending' && psMap[p.phase_id] !== 'active')
      );
    } else if (col.id === 'planned') {
      // Planned: pending plans in active phases
      result[col.id] = localPlans.value.filter(
        (p) => p.status === 'pending' && psMap[p.phase_id] === 'active'
      );
    } else {
      // Standard status match
      result[col.id] = localPlans.value.filter((p) => p.status === col.status);
    }
  }

  return result;
});

// Handle plan moved between columns
function onPlanMoved(planId: string, newStatus: string) {
  const plan = localPlans.value.find((p) => p.id === planId);
  if (!plan) return;

  const oldStatus = plan.status;

  // Backlog <-> Planned moves are both 'pending' -- no API call needed
  if (oldStatus === 'pending' && newStatus === 'pending') {
    return;
  }

  // Optimistic local update
  plan.status = newStatus as GrdPlan['status'];

  // Bubble up to parent for API call
  emit('planStatusChanged', planId, newStatus);
}
</script>

<template>
  <div class="kanban-board">
    <KanbanColumn
      v-for="col in COLUMNS"
      :key="col.id"
      :column-id="col.id"
      :column-label="col.label"
      :column-status="col.status"
      :plans="columnPlans[col.id] || []"
      :phases="phases"
      :phase-lookup="phaseLookup"
      @plan-moved="onPlanMoved"
      @quick-add="(title: string, status: string) => emit('quickAdd', title, status)"
    />
  </div>
</template>

<style scoped>
.kanban-board {
  display: flex;
  gap: 16px;
  padding: 16px 0;
  overflow-x: auto;
  min-height: 500px;
}

/* Responsive: allow horizontal scrolling on narrow screens */
@media (max-width: 1400px) {
  .kanban-board {
    padding-bottom: 8px;
  }
}
</style>
