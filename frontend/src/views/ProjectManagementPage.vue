<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Project, GrdMilestone, GrdPhase, GrdPlan } from '../services/api';
import { projectApi, grdApi } from '../services/api';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import MilestoneOverview from '../components/grd/MilestoneOverview.vue';
import KanbanBoard from '../components/grd/KanbanBoard.vue';
import ProjectSessionPanel from '../components/sessions/ProjectSessionPanel.vue';

const props = defineProps<{
  projectId?: string;
}>();

const route = useRoute();
const router = useRouter();
const projectId = computed(() => (route.params.projectId as string) || props.projectId || '');

const showToast = useToast();

// State
const activeTab = ref<'kanban' | 'sessions'>('kanban');
const project = ref<Project | null>(null);
const milestones = ref<GrdMilestone[]>([]);
const phases = ref<GrdPhase[]>([]);
const plans = ref<GrdPlan[]>([]);
const selectedMilestoneId = ref<string | null>(null);
const isLoading = ref(true);

// Computed
const selectedMilestone = computed(() =>
  milestones.value.find((m) => m.id === selectedMilestoneId.value) ?? null
);

const filteredPhases = computed(() => {
  if (!selectedMilestoneId.value) return phases.value;
  return phases.value.filter((p) => p.milestone_id === selectedMilestoneId.value);
});

const filteredPlans = computed(() => {
  const phaseIds = new Set(filteredPhases.value.map((p) => p.id));
  return plans.value.filter((p) => phaseIds.has(p.phase_id));
});

const breadcrumbs = computed(() => [
  { label: 'Projects', action: () => router.push({ name: 'projects' }) },
  { label: project.value?.name || 'Project', action: () => router.push({ name: 'project-dashboard', params: { projectId: projectId.value } }) },
  { label: 'Management' },
]);

// WebMCP page-specific tool: exposes kanban board state to verification agents
useWebMcpTool({
  name: 'agented_project_get_kanban_state',
  description:
    'Returns the current state of the project kanban board including plan cards grouped by status column',
  page: 'ProjectManagement',
  execute: async () => {
    const plansByStatus: Record<string, { id: string; title: string; phase_id: string }[]> = {};
    for (const plan of filteredPlans.value) {
      const status = plan.status || 'unknown';
      if (!plansByStatus[status]) plansByStatus[status] = [];
      plansByStatus[status].push({
        id: plan.id,
        title: plan.title,
        phase_id: plan.phase_id,
      });
    }
    return {
      content: [
        {
          type: 'text' as const,
          text: JSON.stringify({
            project_id: projectId.value,
            milestone_id: selectedMilestoneId.value,
            milestone_title: selectedMilestone.value?.title ?? null,
            plan_count: filteredPlans.value.length,
            phase_count: filteredPhases.value.length,
            columns: ['backlog', 'planned', 'in_progress', 'in_review', 'done'],
            plans_by_status: plansByStatus,
          }),
        },
      ],
    };
  },
  deps: [filteredPlans, filteredPhases],
});

// Data loading
async function loadData() {
  isLoading.value = true;
  try {
    const [projectData, msRes] = await Promise.all([
      projectApi.get(projectId.value),
      grdApi.listMilestones(projectId.value),
    ]);
    project.value = projectData;
    milestones.value = msRes.milestones || [];

    // Auto-select first milestone if none selected
    if (!selectedMilestoneId.value && milestones.value.length > 0) {
      selectedMilestoneId.value = milestones.value[0].id;
    }

    await loadPhasesAndPlans();
    return project.value;
  } finally {
    isLoading.value = false;
  }
}

async function loadPhasesAndPlans() {
  try {
    const [phRes, plRes] = await Promise.all([
      grdApi.listPhases(projectId.value, selectedMilestoneId.value ?? undefined),
      grdApi.listPlans(projectId.value),
    ]);
    phases.value = phRes.phases || [];
    plans.value = plRes.plans || [];
  } catch (err) {
    showToast('Failed to load phases and plans', 'error');
  }
}

async function handlePlanStatusChanged(planId: string, newStatus: string) {
  try {
    await grdApi.updatePlanStatus(projectId.value, planId, newStatus);
    showToast('Plan status updated', 'success');
  } catch (err) {
    showToast('Failed to update plan status', 'error');
    // Revert: re-fetch data to reset local state
    await loadPhasesAndPlans();
  }
}

// Reload phases/plans when milestone changes
watch(selectedMilestoneId, () => {
  if (!isLoading.value) {
    loadPhasesAndPlans();
  }
});

</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="project management">
    <template #default="{ reload: _reload }">
  <div class="project-management-page">
    <AppBreadcrumb :items="breadcrumbs" />

    <template v-if="project">
      <PageHeader title="Project Management" :subtitle="project?.name || undefined">
        <template #actions>
          <select
            v-if="milestones.length > 1"
            v-model="selectedMilestoneId"
            class="milestone-select"
          >
            <option v-for="ms in milestones" :key="ms.id" :value="ms.id">
              {{ ms.title }} ({{ ms.version }})
            </option>
          </select>
          <button class="btn btn-sm" @click="router.push({ name: 'project-dashboard', params: { projectId: projectId } })">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            Dashboard
          </button>
        </template>
      </PageHeader>

      <div class="tab-bar">
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'kanban' }"
          @click="activeTab = 'kanban'"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <rect x="3" y="3" width="7" height="7" />
            <rect x="14" y="3" width="7" height="7" />
            <rect x="3" y="14" width="7" height="7" />
            <rect x="14" y="14" width="7" height="7" />
          </svg>
          Kanban
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'sessions' }"
          @click="activeTab = 'sessions'"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <polyline points="4 17 10 11 4 5" />
            <line x1="12" y1="19" x2="20" y2="19" />
          </svg>
          Sessions
        </button>
      </div>

      <template v-if="activeTab === 'kanban'">
        <MilestoneOverview
          :milestone="selectedMilestone"
          :phases="filteredPhases"
          :plans="filteredPlans"
        />

        <KanbanBoard
          :project-id="projectId"
          :milestone-id="selectedMilestoneId"
          :phases="filteredPhases"
          :plans="filteredPlans"
          @plan-status-changed="handlePlanStatusChanged"
        />
      </template>

      <ProjectSessionPanel
        v-else-if="activeTab === 'sessions'"
        :project-id="projectId"
      />
    </template>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.project-management-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.milestone-select {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.85rem;
  font-family: inherit;
}

.milestone-select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.tab-bar {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  width: fit-content;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s ease;
}

.tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-secondary);
}

.tab-btn.active {
  color: var(--text-primary);
  background: var(--bg-secondary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.tab-btn svg {
  flex-shrink: 0;
}
</style>
