<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Project, GrdMilestone, GrdPhase, GrdPlan, ConversationMessage, AuthenticatedEventSource } from '../services/api';
import { projectApi, grdApi } from '../services/api';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import MilestoneOverview from '../components/grd/MilestoneOverview.vue';
import KanbanBoard from '../components/grd/KanbanBoard.vue';
import ProjectSessionPanel from '../components/sessions/ProjectSessionPanel.vue';
import ProjectSuperAgentSessions from '../components/sessions/ProjectSuperAgentSessions.vue';
import { AiChatPanelManaged as AiChatPanel } from '@ai-accounts/vue-styled';

const props = defineProps<{
  projectId?: string;
}>();

const route = useRoute();
const router = useRouter();
const projectId = computed(() => (route.params.projectId as string) || props.projectId || '');

const showToast = useToast();
const { t } = useI18n();

// State
// Sessions tab opens by default — it's the live work surface
// (chat panel + active claude session). Kanban is reference state
// and reads fine on demand. v0.7.52.
const activeTab = ref<'kanban' | 'sessions'>('sessions');
const project = ref<Project | null>(null);
const milestones = ref<GrdMilestone[]>([]);
const phases = ref<GrdPhase[]>([]);
const plans = ref<GrdPlan[]>([]);
const selectedMilestoneId = ref<string | null>(null);
const isLoading = ref(true);

// Chat panel state
const showChatPanel = ref(false);
const chatMessages = ref<ConversationMessage[]>([]);
const chatInput = ref('');
const chatIsProcessing = ref(false);
const chatStreamingContent = ref('');
const chatSessionId = ref<string | null>(null);
const chatSuperAgentId = ref<string | null>(null);
// AiChatPanel CLI runner toggle. Default ON because project-management
// chat is the agent-driven manager talking to the project's worktree —
// without tool privileges the answers can only describe, not act.
// Flipping the pill OFF falls back to CLIProxy pure-token chat.
const chatUseCliRunner = ref(true);
let chatEventSource: AuthenticatedEventSource | null = null;
let planChangedDebounce: ReturnType<typeof setTimeout> | null = null;

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
    showToast(t('projectManagement.loadPhasesError'), 'error');
  }
}

async function handlePlanStatusChanged(planId: string, newStatus: string) {
  try {
    await grdApi.updatePlanStatus(projectId.value, planId, newStatus);
    showToast(t('projectManagement.planStatusUpdated'), 'success');
  } catch (err) {
    showToast(t('projectManagement.updatePlanStatusError'), 'error');
    // Revert: re-fetch data to reset local state
    await loadPhasesAndPlans();
  }
}

async function handleQuickAdd(title: string, status: string) {
  // Use first phase as default target
  const targetPhase = filteredPhases.value[0];
  if (!targetPhase) {
    showToast(t('projectManagement.createMilestoneFirst'), 'info');
    return;
  }
  try {
    await grdApi.createPlan(projectId.value, {
      phase_id: targetPhase.id,
      title,
      status,
    });
    showToast(t('projectManagement.cardCreated'), 'success');
    await loadPhasesAndPlans();
  } catch (err) {
    showToast(t('projectManagement.createCardError'), 'error');
  }
}

async function handleCreatePhase(name: string, goal: string) {
  if (!selectedMilestoneId.value) {
    showToast(t('projectManagement.noMilestoneSelected'), 'error');
    return;
  }
  try {
    await grdApi.createPhase(projectId.value, {
      milestone_id: selectedMilestoneId.value,
      name,
      goal: goal || undefined,
    });
    showToast(t('projectManagement.phaseCreated'), 'success');
    await loadPhasesAndPlans();
  } catch (err) {
    showToast(t('projectManagement.createPhaseError'), 'error');
  }
}

// Reload phases/plans when milestone changes
watch(selectedMilestoneId, () => {
  if (!isLoading.value) {
    loadPhasesAndPlans();
  }
});

// --- Chat panel logic ---

function toggleChatPanel() {
  showChatPanel.value = !showChatPanel.value;
}

function closeChatStream() {
  if (chatEventSource) {
    chatEventSource.close();
    chatEventSource = null;
  }
}

function connectChatStream() {
  closeChatStream();
  chatEventSource = grdApi.streamProjectChat(projectId.value);

  chatEventSource.addEventListener('state_delta', (event: Event) => {
    const msgEvent = event as MessageEvent;
    try {
      const data = JSON.parse(msgEvent.data);
      handleChatDelta(data);
    } catch (e) {
      console.warn('[ProjectChat] Failed to parse state_delta:', e);
    }
  });

  chatEventSource.addEventListener('error', () => {
    // EventSource auto-reconnects
  });
}

function handleChatDelta(data: { type: string; [key: string]: unknown }) {
  switch (data.type) {
    case 'message': {
      if (data.role && data.content) {
        const isDuplicate = chatMessages.value.some(
          (m) => m.content === data.content && m.role === data.role,
        );
        if (!isDuplicate) {
          chatMessages.value.push({
            role: data.role as 'user' | 'assistant',
            content: data.content as string,
            timestamp: (data.timestamp as string) || new Date().toISOString(),
          });
        }
      }
      break;
    }
    case 'content_delta': {
      if (data.content) {
        chatStreamingContent.value += data.content as string;
      }
      break;
    }
    case 'finish': {
      const finalContent = (data.content as string) || chatStreamingContent.value;
      if (finalContent) {
        chatMessages.value.push({
          role: 'assistant',
          content: finalContent,
          timestamp: new Date().toISOString(),
        });
      }
      chatStreamingContent.value = '';
      chatIsProcessing.value = false;
      break;
    }
    case 'status_change': {
      if (data.status === 'streaming' || data.status === 'processing') {
        chatIsProcessing.value = true;
      } else if (data.status === 'idle' || data.status === 'error') {
        chatIsProcessing.value = false;
      }
      break;
    }
    case 'error': {
      chatIsProcessing.value = false;
      showToast((data.message as string) || t('projectManagement.chatError'), 'error');
      break;
    }
    case 'plan_changed': {
      // Debounced kanban refresh when AI modifies plans
      if (planChangedDebounce) clearTimeout(planChangedDebounce);
      planChangedDebounce = setTimeout(() => {
        loadPhasesAndPlans();
      }, 300);
      break;
    }
  }
}

async function handleChatSend() {
  const content = chatInput.value.trim();
  if (!content) return;

  // Optimistic user message
  chatMessages.value.push({
    role: 'user',
    content,
    timestamp: new Date().toISOString(),
  });
  chatInput.value = '';
  chatIsProcessing.value = true;
  chatStreamingContent.value = '';

  try {
    const res = await grdApi.sendProjectChat(projectId.value, {
      content,
      milestone_id: selectedMilestoneId.value ?? undefined,
      useCliAgent: chatUseCliRunner.value,
    });
    chatSessionId.value = res.session_id;
    chatSuperAgentId.value = res.super_agent_id;

    // Connect SSE stream if not already connected
    if (!chatEventSource) {
      connectChatStream();
    }
  } catch (err) {
    chatMessages.value.pop(); // Remove optimistic message
    chatIsProcessing.value = false;
    showToast(t('projectManagement.sendChatError'), 'error');
  }
}

function handleChatKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    handleChatSend();
  }
}

onUnmounted(() => {
  closeChatStream();
  if (planChangedDebounce) clearTimeout(planChangedDebounce);
});
</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="project management">
    <template #default="{ reload: _reload }">
  <div class="project-management-page">

    <!-- Wrap multi-root v-if/v-else-if branches in `display:contents` divs so
         Vue's parent block sees a stable single-root vnode in each branch.
         Multi-root `<template v-if>` fragments shift the parent's
         `dynamicChildren` count when toggled, corrupting `patchBlockChildren`
         (TypeError reading 'el' on undefined). Same fix as EntityLayout.vue
         and BackendDetailPage.vue. -->
    <div v-if="project" class="project-management-page__content">
      <PageHeader :title="t('projectManagement.title')" :subtitle="project?.name || undefined">
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
            v-if="activeTab === 'kanban'"
            class="btn btn-sm"
            :class="{ 'btn-active': showChatPanel }"
            @click="toggleChatPanel"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            {{ t('projectManagement.chat') }}
          </button>
          <button class="btn btn-sm" @click="router.push({ name: 'project-dashboard', params: { projectId: projectId } })">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            {{ t('projectManagement.dashboard') }}
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
          {{ t('projectManagement.kanban') }}
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
          {{ t('projectManagement.sessions') }}
        </button>
      </div>

      <div v-if="activeTab === 'kanban'" class="tab-pane">
        <MilestoneOverview
          :milestone="selectedMilestone"
          :phases="filteredPhases"
          :plans="filteredPlans"
          @create-phase="handleCreatePhase"
        />

        <div class="kanban-chat-layout" :class="{ 'chat-open': showChatPanel }">
          <div class="kanban-main">
            <KanbanBoard
              :project-id="projectId"
              :milestone-id="selectedMilestoneId"
              :phases="filteredPhases"
              :plans="filteredPlans"
              @plan-status-changed="handlePlanStatusChanged"
              @quick-add="handleQuickAdd"
            />
          </div>

          <div v-if="showChatPanel" class="chat-side-panel">
            <div class="chat-panel-header">
              <span class="chat-panel-title">{{ t('projectManagement.aiManager') }}</span>
              <button class="chat-panel-close" @click="showChatPanel = false">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
            <AiChatPanel
              :messages="chatMessages"
              :is-processing="chatIsProcessing"
              :streaming-content="chatStreamingContent"
              :input-message="chatInput"
              :conversation-id="chatSessionId"
              :can-finalize="false"
              :is-finalizing="false"
              :assistant-icon-paths="['M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z']"
              :input-placeholder="t('projectManagement.chatPlaceholder')"
              entity-label="project"
              banner-title=""
              banner-button-label=""
              :read-only="false"
              :use-smart-scroll="true"
              :use-cli-runner="chatUseCliRunner"
              @update:input-message="chatInput = $event"
              @update:use-cli-runner="chatUseCliRunner = $event"
              @send="handleChatSend"
              @keydown="handleChatKeydown"
            />
          </div>
        </div>
      </div>

      <div v-else-if="activeTab === 'sessions'" class="tab-pane">
        <!-- Two parallel session systems coexist here:
             * Sketch → SuperAgent routing → ``super_agent_sessions``
               table — surfaced by ``ProjectSuperAgentSessions`` (read-
               only list with playground links).
             * GRD project sessions → ``project_sessions`` table — a
               real claude subprocess. ``ProjectSessionPanel`` renders
               direct-mode as chat bubbles (since v0.7.50) AND keeps
               the History sidebar + ExecutionTypeSelector + pause/
               resume controls for ralph_loop and team_spawn. v0.7.55
               dropped ``GrdSessionChatView``: its behavior was a
               proper subset of this panel's direct mode after the
               v0.7.50 / v0.7.54 fixes converged the two surfaces. -->
        <ProjectSuperAgentSessions :project-id="projectId" />
        <ProjectSessionPanel :project-id="projectId" />
      </div>
    </div>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
/* Layout-invisible wrappers for the v-if branches in the template.
   `display: contents` removes the wrapper from the box tree, so the
   children participate in `.project-management-page`'s flex column
   exactly as they did when the branches were `<template>` fragments. */
.project-management-page__content,
.tab-pane {
  display: contents;
}

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

.btn-active {
  color: var(--accent-cyan) !important;
  border-color: var(--accent-cyan) !important;
}

/* Kanban + Chat layout */
.kanban-chat-layout {
  display: flex;
  gap: 16px;
  min-height: 0;
}

.kanban-main {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}

.chat-side-panel {
  width: 340px;
  min-width: 340px;
  max-width: 340px;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
  height: calc(100vh - 280px);
}

.chat-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.chat-panel-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
}

.chat-panel-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.chat-panel-close:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.chat-side-panel :deep(.ai-chat-panel) {
  flex: 1;
  min-height: 0;
  border: none;
  border-radius: 0;
}
</style>
