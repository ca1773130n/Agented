<script setup lang="ts">
import { ref, onMounted, inject } from 'vue';
import type { Trigger, BackendCheck, ProjectPath, Project, Team } from '../services/api';
import { triggerApi, utilityApi, projectApi, teamApi, backendApi, ApiError } from '../services/api';
import AddTriggerModal from '../components/triggers/AddTriggerModal.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import BackendStatusCard from '../components/triggers/BackendStatusCard.vue';
import TriggerList from '../components/triggers/TriggerList.vue';
import TriggerDetailPanel from '../components/triggers/TriggerDetailPanel.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const showToast = useToast();
const refreshTriggers = inject('refreshTriggers', () => Promise.resolve()) as () => Promise<void>;

const triggers = ref<Trigger[]>([]);
const isLoading = ref(true);
const claudeStatus = ref<BackendCheck | null>(null);
const opencodeStatus = ref<BackendCheck | null>(null);
const selectedTriggerId = ref<string | null>(null);
const selectedTrigger = ref<Trigger | null>(null);
const triggerPaths = ref<ProjectPath[]>([]);
const showAddTriggerModal = ref(false);
const projects = ref<Project[]>([]);
const teams = ref<Team[]>([]);
const availableBackends = ref<Array<{ id: string; name: string; type: string }>>([]);
const availableAccounts = ref<Array<{ id: number; account_name: string; backend_id: string }>>([]);

// Confirm delete state
const showDeleteConfirm = ref(false);
const pendingDeleteId = ref<string | null>(null);

useWebMcpTool({
  name: 'hive_trigger_mgmt_get_state',
  description: 'Returns the current state of the TriggerManagement',
  page: 'TriggerManagement',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'TriggerManagement',
        isLoading: isLoading.value,
        triggersCount: triggers.value.length,
        selectedTriggerId: selectedTriggerId.value,
        selectedTriggerName: selectedTrigger.value?.name ?? null,
        showAddTriggerModal: showAddTriggerModal.value,
        showDeleteConfirm: showDeleteConfirm.value,
        claudeInstalled: claudeStatus.value?.installed ?? null,
        opencodeInstalled: opencodeStatus.value?.installed ?? null,
      }),
    }],
  }),
  deps: [isLoading, triggers, selectedTriggerId, selectedTrigger, showAddTriggerModal, showDeleteConfirm, claudeStatus, opencodeStatus],
});

async function checkBackends() {
  try {
    const [claude, opencode] = await Promise.all([
      utilityApi.checkBackend('claude').catch(() => ({ backend: 'claude', installed: false })),
      utilityApi.checkBackend('opencode').catch(() => ({ backend: 'opencode', installed: false })),
    ]);
    claudeStatus.value = claude as BackendCheck;
    opencodeStatus.value = opencode as BackendCheck;
  } catch { /* Ignore */ }
}

async function loadTriggers() {
  isLoading.value = true;
  try {
    const data = await triggerApi.list();
    triggers.value = data.triggers || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load triggers';
    showToast(message, 'error');
  } finally { isLoading.value = false; }
}

async function selectTrigger(triggerId: string) {
  selectedTriggerId.value = triggerId;
  try {
    const trig = await triggerApi.get(triggerId);
    selectedTrigger.value = trig;
    triggerPaths.value = trig.paths || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load trigger details';
    showToast(message, 'error');
  }
}

async function toggleTriggerEnabled(triggerId: string, enabled: number) {
  try {
    await triggerApi.update(triggerId, { enabled });
    await loadTriggers();
    showToast(enabled ? 'Trigger enabled' : 'Trigger disabled', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update trigger';
    showToast(message, 'error');
  }
}

function deleteTrigger(triggerId: string) {
  pendingDeleteId.value = triggerId;
  showDeleteConfirm.value = true;
}

async function confirmDeleteTrigger() {
  const triggerId = pendingDeleteId.value;
  showDeleteConfirm.value = false;
  pendingDeleteId.value = null;
  if (!triggerId) return;
  try {
    await triggerApi.delete(triggerId);
    if (selectedTriggerId.value === triggerId) {
      selectedTriggerId.value = null;
      selectedTrigger.value = null;
    }
    await loadTriggers();
    await refreshTriggers();
    showToast('Trigger deleted', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to delete trigger';
    showToast(message, 'error');
  }
}

async function onTriggerSaved() {
  await loadTriggers();
  if (selectedTriggerId.value) {
    const trig = await triggerApi.get(selectedTriggerId.value);
    selectedTrigger.value = trig;
  }
}

async function onPathChanged() {
  if (selectedTriggerId.value) {
    await selectTrigger(selectedTriggerId.value);
    await loadTriggers();
  }
}

async function onTriggerCreated() {
  showAddTriggerModal.value = false;
  await loadTriggers();
  await refreshTriggers();
}

async function loadProjects() {
  try {
    const data = await projectApi.list();
    projects.value = (data.projects || []).filter((p: Project) => p.github_repo);
  } catch { projects.value = []; }
}

async function loadTeams() {
  try {
    const data = await teamApi.list();
    teams.value = data.teams || [];
  } catch { teams.value = []; }
}

async function loadBackendsAndAccounts() {
  try {
    const data = await backendApi.list();
    const backends = data.backends || [];
    availableBackends.value = backends.map(b => ({ id: b.id, name: b.name, type: b.type }));
    const allAccounts: Array<{ id: number; account_name: string; backend_id: string }> = [];
    for (const b of backends) {
      try {
        const detail = await backendApi.get(b.id);
        if (detail.accounts) {
          allAccounts.push(...detail.accounts.map(a => ({ id: a.id, account_name: a.account_name, backend_id: b.id })));
        }
      } catch { /* skip */ }
    }
    availableAccounts.value = allAccounts;
  } catch {
    availableBackends.value = [];
    availableAccounts.value = [];
  }
}

onMounted(() => {
  checkBackends();
  loadTriggers();
  loadProjects();
  loadTeams();
  loadBackendsAndAccounts();
});
</script>

<template>
  <div class="trigger-management">
    <AppBreadcrumb :items="[{ label: 'Triggers' }]" />

    <BackendStatusCard :claudeStatus="claudeStatus" :opencodeStatus="opencodeStatus" />

    <TriggerList
      :triggers="triggers"
      :selectedTriggerId="selectedTriggerId"
      :isLoading="isLoading"
      @selectTrigger="selectTrigger"
      @toggleEnabled="toggleTriggerEnabled"
      @deleteTrigger="deleteTrigger"
      @addTrigger="showAddTriggerModal = true"
    />

    <TriggerDetailPanel
      v-if="selectedTrigger"
      :selectedTrigger="selectedTrigger"
      :triggerPaths="triggerPaths"
      :projects="projects"
      :teams="teams"
      :availableBackends="availableBackends"
      :availableAccounts="availableAccounts"
      @saved="onTriggerSaved"
      @pathChanged="onPathChanged"
    />

    <AddTriggerModal
      v-if="showAddTriggerModal"
      @close="showAddTriggerModal = false"
      @created="onTriggerCreated"
    />

    <ConfirmModal
      :open="showDeleteConfirm"
      title="Delete Trigger"
      message="Delete this trigger?"
      confirm-label="Delete"
      variant="danger"
      @confirm="confirmDeleteTrigger"
      @cancel="showDeleteConfirm = false"
    />
  </div>
</template>

<style scoped>
.trigger-management { display: flex; flex-direction: column; gap: 24px; width: 100%; animation: fadeIn 0.4s ease; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
