<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Project, GrdMilestone, GrdPhase, GrdPlan } from '../services/api';
import { projectApi, grdApi } from '../services/api';
import { useToast } from '../composables/useToast';
import { usePlanningSession } from '../composables/usePlanningSession';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import MilestoneOverview from '../components/grd/MilestoneOverview.vue';
import PlanningCommandBar from '../components/grd/PlanningCommandBar.vue';
import PlanningSessionPanel from '../components/grd/PlanningSessionPanel.vue';

const props = defineProps<{
  projectId?: string;
}>();

const route = useRoute();
const router = useRouter();
const projectId = computed(() => (route.params.projectId as string) || props.projectId || '');

const showToast = useToast();

// State
const project = ref<Project | null>(null);
const milestones = ref<GrdMilestone[]>([]);
const phases = ref<GrdPhase[]>([]);
const plans = ref<GrdPlan[]>([]);
const selectedMilestoneId = ref<string | null>(null);
const grdInitStatus = ref<string>('none');
const showSessionPanel = ref(false);

// Planning session composable
const planning = usePlanningSession(projectId);

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
  {
    label: project.value?.name || 'Project',
    action: () =>
      router.push({ name: 'project-dashboard', params: { projectId: projectId.value } }),
  },
  { label: 'Planning' },
]);

// Data loading
async function loadData() {
  try {
    const [projectData, msRes, statusRes] = await Promise.all([
      projectApi.get(projectId.value),
      grdApi.listMilestones(projectId.value),
      grdApi.getPlanningStatus(projectId.value),
    ]);
    project.value = projectData;
    milestones.value = msRes.milestones || [];
    grdInitStatus.value = statusRes.grd_init_status || 'none';

    if (!selectedMilestoneId.value && milestones.value.length > 0) {
      selectedMilestoneId.value = milestones.value[0].id;
    }

    await loadPhasesAndPlans();
    return project.value;
  } catch (err) {
    showToast('Failed to load planning data', 'error');
    throw err;
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
  } catch {
    showToast('Failed to load phases and plans', 'error');
  }
}

// Command dispatch
function handleInvokeCommand(command: string, args?: Record<string, string>) {
  planning.invokeCommand(command, args);
  showSessionPanel.value = true;
}

function handlePhaseCommand(phaseNumber: number, command: string) {
  handleInvokeCommand(command, { phase: String(phaseNumber) });
}

function handleCreatePhase(name: string, goal: string) {
  if (!selectedMilestoneId.value) {
    showToast('No milestone selected', 'error');
    return;
  }
  grdApi
    .createPhase(projectId.value, {
      milestone_id: selectedMilestoneId.value,
      name,
      goal: goal || undefined,
    })
    .then(() => {
      showToast('Phase created', 'success');
      loadPhasesAndPlans();
    })
    .catch(() => {
      showToast('Failed to create phase', 'error');
    });
}

function handleClearSession() {
  planning.clearOutput();
  showSessionPanel.value = false;
}

// Refresh data when session completes
watch(
  () => planning.status.value,
  (newStatus) => {
    if (newStatus === 'complete') {
      grdApi.sync(projectId.value).finally(() => {
        loadPhasesAndPlans();
      });
    }
  }
);

// Reload phases/plans when milestone changes
watch(selectedMilestoneId, () => {
  loadPhasesAndPlans();
});
</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="planning">
    <template #default>
      <div class="planning-page">
        <AppBreadcrumb :items="breadcrumbs" />

        <PageHeader title="Planning" :subtitle="project?.name || undefined">
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
            <button
              class="btn btn-sm"
              @click="
                router.push({
                  name: 'project-management',
                  params: { projectId: projectId },
                })
              "
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                width="16"
                height="16"
              >
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
              </svg>
              Kanban
            </button>
          </template>
        </PageHeader>

        <div class="planning-layout" :class="{ 'session-open': showSessionPanel }">
          <div class="planning-left">
            <MilestoneOverview
              :milestone="selectedMilestone"
              :phases="filteredPhases"
              :plans="filteredPlans"
              @create-phase="handleCreatePhase"
              @phase-command="handlePhaseCommand"
            />
            <PlanningCommandBar
              :status="planning.status.value"
              :grd-init-status="grdInitStatus"
              @invoke="handleInvokeCommand"
            />
          </div>
          <div v-if="showSessionPanel" class="planning-right">
            <PlanningSessionPanel
              :output-lines="planning.outputLines.value"
              :status="planning.status.value"
              :current-question="planning.currentQuestion.value"
              :exit-code="planning.exitCode.value"
              @send-answer="planning.sendAnswer"
              @stop="planning.stopSession"
              @clear="handleClearSession"
            />
          </div>
        </div>
      </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.planning-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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

.planning-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 200px);
}

.planning-left {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.planning-right {
  width: 420px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}
</style>
