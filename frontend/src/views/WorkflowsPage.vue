<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { Workflow } from '../services/api';
import { workflowApi, ApiError } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import StatusBadge from '../components/base/StatusBadge.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpPageTools } from '../webmcp/useWebMcpPageTools';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();

const showToast = useToast();

const workflows = ref<Workflow[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const searchQuery = ref('');
const showCreateModal = ref(false);
const showDeleteConfirm = ref(false);
const createModalRef = ref<HTMLElement | null>(null);
const deleteModalRef = ref<HTMLElement | null>(null);
const workflowToDelete = ref<Workflow | null>(null);
const createForm = ref({ name: '', description: '', trigger_type: 'manual' });

useFocusTrap(createModalRef, showCreateModal);
useFocusTrap(deleteModalRef, showDeleteConfirm);

useWebMcpPageTools({
  page: 'WorkflowsPage',
  domain: 'workflows',
  stateGetter: () => ({
    items: workflows.value,
    itemCount: workflows.value.length,
    isLoading: isLoading.value,
    error: loadError.value,
    searchQuery: searchQuery.value,
  }),
  modalGetter: () => ({
    showCreateModal: showCreateModal.value,
    showDeleteConfirm: showDeleteConfirm.value,
    formValues: createForm.value,
  }),
  modalActions: {
    openCreate: () => { showCreateModal.value = true; },
    openDelete: (id: string) => {
      const wf = workflows.value.find((w: any) => w.id === id);
      if (wf) { workflowToDelete.value = wf; showDeleteConfirm.value = true; }
    },
  },
  deps: [workflows, searchQuery],
});

useWebMcpTool({
  name: 'agented_workflows_toggle_enabled',
  description: 'Toggles the enabled state of a workflow',
  page: 'WorkflowsPage',
  inputSchema: { type: 'object', properties: { workflowId: { type: 'string', description: 'ID of the workflow to toggle' } }, required: ['workflowId'] },
  execute: async (args) => {
    const wf = workflows.value.find((w: any) => w.id === args.workflowId);
    if (!wf) {
      return { content: [{ type: 'text' as const, text: JSON.stringify({ success: false, error: `Workflow ${args.workflowId} not found` }) }] };
    }
    await toggleEnabled(wf);
    return { content: [{ type: 'text' as const, text: JSON.stringify({ success: true, enabled: !!wf.enabled }) }] };
  },
  deps: [workflows],
});

const filteredWorkflows = computed(() => {
  const q = searchQuery.value.toLowerCase().trim();
  if (!q) return workflows.value;
  return workflows.value.filter(
    (wf) =>
      wf.name.toLowerCase().includes(q) ||
      (wf.description && wf.description.toLowerCase().includes(q))
  );
});

async function loadWorkflows() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await workflowApi.list();
    workflows.value = data.workflows || [];
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : 'Failed to load workflows';
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function createWorkflow() {
  if (!createForm.value.name.trim()) {
    showToast('Name is required', 'error');
    return;
  }
  try {
    await workflowApi.create({
      name: createForm.value.name,
      description: createForm.value.description || undefined,
      trigger_type: createForm.value.trigger_type,
    });
    showToast('Workflow created successfully', 'success');
    showCreateModal.value = false;
    createForm.value = { name: '', description: '', trigger_type: 'manual' };
    await loadWorkflows();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to create workflow', 'error');
    }
  }
}

function confirmDelete(wf: Workflow) {
  workflowToDelete.value = wf;
  showDeleteConfirm.value = true;
}

async function deleteWorkflow() {
  if (!workflowToDelete.value) return;
  try {
    await workflowApi.delete(workflowToDelete.value.id);
    showToast(`Workflow "${workflowToDelete.value.name}" deleted`, 'success');
    showDeleteConfirm.value = false;
    workflowToDelete.value = null;
    await loadWorkflows();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to delete workflow', 'error');
    }
  }
}

async function toggleEnabled(wf: Workflow) {
  try {
    const newVal = wf.enabled ? 0 : 1;
    await workflowApi.update(wf.id, { enabled: newVal });
    wf.enabled = newVal;
    showToast(`Workflow ${wf.enabled ? 'enabled' : 'disabled'}`, 'success');
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to update workflow', 'error');
    }
  }
}

function getTriggerBadgeClass(triggerType: string): string {
  switch (triggerType) {
    case 'manual': return 'trigger-manual';
    case 'cron': return 'trigger-cron';
    case 'poll': return 'trigger-poll';
    case 'file_watch': return 'trigger-file-watch';
    case 'completion': return 'trigger-completion';
    default: return '';
  }
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString();
}

onMounted(loadWorkflows);
</script>

<template>
  <div class="workflows-page">
    <PageHeader title="Workflows" subtitle="Visual DAG-based workflow automation with triggers, conditions, and agent orchestration">
      <template #actions>
        <div class="search-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search workflows..."
            class="search-input"
          />
        </div>
        <button class="btn btn-primary" @click="showCreateModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Create Workflow
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading workflows..." />

    <ErrorState v-else-if="loadError" title="Failed to load workflows" :message="loadError" @retry="loadWorkflows" />

    <EmptyState v-else-if="workflows.length === 0" title="No workflows yet" description="Create your first workflow to get started with visual automation">
      <template #icon>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="8" y="2" width="8" height="5" rx="1"/>
          <rect x="8" y="10" width="8" height="5" rx="1"/>
          <rect x="8" y="18" width="8" height="5" rx="1"/>
          <line x1="12" y1="7" x2="12" y2="10"/>
          <line x1="12" y1="15" x2="12" y2="18"/>
        </svg>
      </template>
      <template #actions>
        <button class="btn btn-primary" @click="showCreateModal = true">Create Your First Workflow</button>
      </template>
    </EmptyState>

    <EmptyState v-else-if="filteredWorkflows.length === 0 && searchQuery" title="No matching workflows" description="Try a different search term" />

    <div v-else class="wf-grid">
      <div
        v-for="wf in filteredWorkflows"
        :key="wf.id"
        class="wf-card"
        @click="router.push({ name: 'workflow-builder', params: { workflowId: wf.id } })"
      >
        <div class="wf-card-header">
          <div class="wf-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="8" y="2" width="8" height="5" rx="1"/>
              <rect x="8" y="10" width="8" height="5" rx="1"/>
              <rect x="8" y="18" width="8" height="5" rx="1"/>
              <line x1="12" y1="7" x2="12" y2="10"/>
              <line x1="12" y1="15" x2="12" y2="18"/>
            </svg>
          </div>
          <div class="wf-info">
            <h3>{{ wf.name }}</h3>
            <div class="wf-badges">
              <span :class="['badge-trigger', getTriggerBadgeClass(wf.trigger_type)]">{{ wf.trigger_type }}</span>
              <StatusBadge :label="wf.enabled ? 'Enabled' : 'Disabled'" :variant="wf.enabled ? 'success' : 'neutral'" />
            </div>
          </div>
        </div>

        <p v-if="wf.description" class="wf-description">{{ wf.description }}</p>

        <div class="wf-meta">
          <div v-if="wf.created_at" class="meta-item">
            <span class="meta-label">Created:</span>
            <span class="meta-value">{{ formatDate(wf.created_at) }}</span>
          </div>
        </div>

        <div class="wf-actions">
          <button class="btn btn-sm" @click.stop="router.push({ name: 'workflow-builder', params: { workflowId: wf.id } })">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
            Edit
          </button>
          <button
            class="btn btn-sm"
            :class="wf.enabled ? 'btn-warning' : 'btn-success'"
            @click.stop="toggleEnabled(wf)"
          >
            {{ wf.enabled ? 'Disable' : 'Enable' }}
          </button>
          <button class="btn btn-sm btn-danger" @click.stop="confirmDelete(wf)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            Delete
          </button>
        </div>
      </div>
    </div>

    <!-- Create Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal" ref="createModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-workflow" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-create-workflow">Create Workflow</h2>
            <button class="modal-close" @click="showCreateModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Name *</label>
              <input v-model="createForm.name" type="text" placeholder="e.g., deploy-pipeline" />
            </div>
            <div class="form-group">
              <label>Description</label>
              <textarea v-model="createForm.description" placeholder="Describe what this workflow does..."></textarea>
            </div>
            <div class="form-group">
              <label>Trigger Type</label>
              <select v-model="createForm.trigger_type">
                <option value="manual">Manual</option>
                <option value="cron">Cron</option>
                <option value="poll">Poll</option>
                <option value="file_watch">File Watch</option>
                <option value="completion">Completion</option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn" @click="showCreateModal = false">Cancel</button>
            <button class="btn btn-primary" @click="createWorkflow">Create</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete Confirmation -->
    <Teleport to="body">
      <div v-if="showDeleteConfirm" ref="deleteModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-delete-workflow" tabindex="-1" @click.self="showDeleteConfirm = false" @keydown.escape="showDeleteConfirm = false">
        <div class="modal modal-small">
          <div class="modal-header">
            <h2 id="modal-title-delete-workflow">Delete Workflow</h2>
          </div>
          <div class="modal-body">
            <p>Are you sure you want to delete "<strong>{{ workflowToDelete?.name }}</strong>"?</p>
            <p class="warning-text">This action cannot be undone. All versions and execution history will be removed.</p>
          </div>
          <div class="modal-footer">
            <button class="btn" @click="showDeleteConfirm = false">Cancel</button>
            <button class="btn btn-danger" @click="deleteWorkflow">Delete</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.workflows-page {
}

.search-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
}

.search-wrapper svg {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.search-input {
  background: transparent;
  border: none;
  font-size: 14px;
  color: var(--text-primary);
  width: 200px;
}

.search-input:focus {
  outline: none;
}

.search-input::placeholder {
  color: var(--text-tertiary);
}

.wf-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.5rem;
}

.wf-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  transition: all 0.2s;
  cursor: pointer;
}

.wf-card:hover {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 20px rgba(0, 212, 255, 0.1);
}

.wf-card-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.wf-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--accent-cyan, #00d4ff), var(--accent-emerald, #00ff88));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.wf-icon svg {
  width: 24px;
  height: 24px;
  color: #fff;
}

.wf-info {
  flex: 1;
  min-width: 0;
}

.wf-info h3 {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 0.5rem 0;
  color: var(--text-primary);
}

.wf-badges {
  display: flex;
  gap: 0.5rem;
}

.badge-trigger {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.trigger-manual {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.trigger-cron {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.trigger-poll {
  background: var(--accent-amber-dim);
  color: var(--accent-amber);
}

.trigger-file-watch {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.trigger-completion {
  background: rgba(136, 136, 136, 0.15);
  color: #888;
}

.wf-description {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin: 0 0 1rem 0;
  line-height: 1.5;
}

.wf-meta {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 1rem;
}

.meta-item {
  font-size: 0.85rem;
}

.meta-label {
  color: var(--text-secondary);
  margin-right: 0.5rem;
}

.meta-value {
  color: var(--text-primary);
}

.wf-actions {
  display: flex;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-subtle);
}

/* Modal styles */
.modal-small {
  max-width: 400px;
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.warning-text {
  color: var(--accent-amber);
  font-size: 0.9rem;
  margin-top: 0.5rem;
}

.btn-warning {
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: #f59e0b;
}

.btn-warning:hover {
  background: rgba(245, 158, 11, 0.25);
}

.btn-success {
  background: rgba(34, 197, 94, 0.15);
  border: 1px solid rgba(34, 197, 94, 0.3);
  color: #22c55e;
}

.btn-success:hover {
  background: rgba(34, 197, 94, 0.25);
}
</style>
