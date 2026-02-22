<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { SuperAgent } from '../services/api';
import { superAgentApi, ApiError } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpPageTools } from '../webmcp/useWebMcpPageTools';

const router = useRouter();

const showToast = useToast();

const superAgents = ref<SuperAgent[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const searchQuery = ref('');
const showCreateModal = ref(false);
const showDeleteConfirm = ref(false);
const createModalRef = ref<HTMLElement | null>(null);
const deleteModalRef = ref<HTMLElement | null>(null);
const agentToDelete = ref<SuperAgent | null>(null);
const createForm = ref({ name: '', description: '', backend_type: 'claude' });

useFocusTrap(createModalRef, showCreateModal);
useFocusTrap(deleteModalRef, showDeleteConfirm);

useWebMcpPageTools({
  page: 'SuperAgentsPage',
  domain: 'super_agents',
  stateGetter: () => ({
    items: superAgents.value,
    itemCount: superAgents.value.length,
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
      const sa = superAgents.value.find((s: any) => s.id === id);
      if (sa) { agentToDelete.value = sa; showDeleteConfirm.value = true; }
    },
  },
  deps: [superAgents, searchQuery],
});

const filteredSuperAgents = computed(() => {
  const q = searchQuery.value.toLowerCase().trim();
  if (!q) return superAgents.value;
  return superAgents.value.filter(
    (sa) =>
      sa.name.toLowerCase().includes(q) ||
      (sa.description && sa.description.toLowerCase().includes(q))
  );
});

async function loadSuperAgents() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await superAgentApi.list();
    superAgents.value = data.super_agents || [];
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : 'Failed to load super agents';
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function createSuperAgent() {
  if (!createForm.value.name.trim()) {
    showToast('Name is required', 'error');
    return;
  }
  try {
    await superAgentApi.create({
      name: createForm.value.name,
      description: createForm.value.description || undefined,
      backend_type: createForm.value.backend_type,
    });
    showToast('SuperAgent created successfully', 'success');
    showCreateModal.value = false;
    createForm.value = { name: '', description: '', backend_type: 'claude' };
    // Super agent created, reload list
    await loadSuperAgents();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to create super agent', 'error');
    }
  }
}

function confirmDelete(sa: SuperAgent) {
  agentToDelete.value = sa;
  showDeleteConfirm.value = true;
}

async function deleteSuperAgent() {
  if (!agentToDelete.value) return;
  try {
    await superAgentApi.delete(agentToDelete.value.id);
    showToast(`SuperAgent "${agentToDelete.value.name}" deleted`, 'success');
    showDeleteConfirm.value = false;
    agentToDelete.value = null;
    // Super agent deleted, reload list
    await loadSuperAgents();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to delete super agent', 'error');
    }
  }
}

function getBackendClass(backendType: string) {
  switch (backendType) {
    case 'claude': return 'backend-claude';
    case 'opencode': return 'backend-opencode';
    case 'gemini': return 'backend-gemini';
    case 'codex': return 'backend-codex';
    default: return '';
  }
}

async function toggleEnabled(sa: SuperAgent, event: Event) {
  event.stopPropagation();
  try {
    await superAgentApi.update(sa.id, { enabled: sa.enabled ? 0 : 1 });
    showToast(`SuperAgent "${sa.name}" ${sa.enabled ? 'disabled' : 'enabled'}`, 'success');
    await loadSuperAgents();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to update super agent', 'error');
    }
  }
}

function getStatusClass(sa: SuperAgent) {
  return sa.enabled ? 'status-active' : 'status-inactive';
}

onMounted(loadSuperAgents);
</script>

<template>
  <div class="super-agents-page">
    <PageHeader title="SuperAgents" subtitle="Persistent session agents with identity documents and inter-agent messaging">
      <template #actions>
        <div class="search-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search super agents..."
            class="search-input"
          />
        </div>
        <button class="btn btn-secondary" @click="router.push({ name: 'explore-super-agents' })">
          Explore SuperAgents
        </button>
        <button class="btn btn-primary" @click="showCreateModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Create SuperAgent
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading super agents..." />

    <ErrorState
      v-else-if="loadError"
      title="Failed to load super agents"
      :message="loadError"
      @retry="loadSuperAgents"
    />

    <EmptyState
      v-else-if="superAgents.length === 0"
      title="No super agents yet"
      description="Create your first SuperAgent to get started"
    >
      <template #actions>
        <button class="btn btn-primary" @click="showCreateModal = true">Create Your First SuperAgent</button>
      </template>
    </EmptyState>

    <EmptyState
      v-else-if="filteredSuperAgents.length === 0"
      title="No matching super agents"
      description="Try a different search term"
    />

    <div v-else class="sa-grid">
      <div
        v-for="sa in filteredSuperAgents"
        :key="sa.id"
        class="sa-card"
        @click="router.push({ name: 'super-agent-playground', params: { superAgentId: sa.id } })"
      >
        <div class="sa-card-header">
          <div class="sa-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="8" r="4"/>
              <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
              <path d="M17 3l2 2-2 2M7 3l-2 2 2 2"/>
            </svg>
          </div>
          <div class="sa-info">
            <h3>{{ sa.name }}</h3>
            <div class="sa-badges">
              <span :class="['badge-backend', getBackendClass(sa.backend_type)]">{{ sa.backend_type }}</span>
              <span :class="['badge-status', getStatusClass(sa)]">{{ sa.enabled ? 'Active' : 'Inactive' }}</span>
            </div>
          </div>
        </div>

        <p v-if="sa.description" class="sa-description">{{ sa.description }}</p>

        <div class="sa-meta">
          <div v-if="sa.preferred_model" class="meta-item">
            <span class="meta-label">Model:</span>
            <span class="meta-value">{{ sa.preferred_model }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Max Sessions:</span>
            <span class="meta-value">{{ sa.max_concurrent_sessions }}</span>
          </div>
        </div>

        <div class="sa-actions">
          <button
            :class="['btn', 'btn-sm', sa.enabled ? 'btn-toggle-active' : 'btn-toggle-inactive']"
            @click.stop="toggleEnabled(sa, $event)"
          >
            {{ sa.enabled ? 'Disable' : 'Enable' }}
          </button>
          <button class="btn btn-sm btn-secondary" @click.stop="router.push({ name: 'super-agent-playground', params: { superAgentId: sa.id } })">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
            Edit
          </button>
          <button class="btn btn-sm btn-danger" @click.stop="confirmDelete(sa)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            Delete
          </button>
        </div>
      </div>
    </div>

    <!-- Create Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal" ref="createModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-superagent" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-create-superagent">Create SuperAgent</h2>
            <button class="modal-close" @click="showCreateModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Name *</label>
              <input v-model="createForm.name" type="text" placeholder="e.g., code-reviewer" />
            </div>
            <div class="form-group">
              <label>Description</label>
              <textarea v-model="createForm.description" placeholder="Describe what this SuperAgent does..."></textarea>
            </div>
            <div class="form-group">
              <label>Backend Type</label>
              <select v-model="createForm.backend_type">
                <option value="claude">Claude</option>
                <option value="opencode">OpenCode</option>
                <option value="gemini">Gemini</option>
                <option value="codex">Codex</option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn" @click="showCreateModal = false">Cancel</button>
            <button class="btn btn-primary" @click="createSuperAgent">Create</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Delete Confirmation -->
    <Teleport to="body">
      <div v-if="showDeleteConfirm" ref="deleteModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-delete-superagent" tabindex="-1" @click.self="showDeleteConfirm = false" @keydown.escape="showDeleteConfirm = false">
        <div class="modal modal-small">
          <div class="modal-header">
            <h2 id="modal-title-delete-superagent">Delete SuperAgent</h2>
          </div>
          <div class="modal-body">
            <p>Are you sure you want to delete "<strong>{{ agentToDelete?.name }}</strong>"?</p>
            <p class="warning-text">This action cannot be undone. All documents and sessions will be removed.</p>
          </div>
          <div class="modal-footer">
            <button class="btn" @click="showDeleteConfirm = false">Cancel</button>
            <button class="btn btn-danger" @click="deleteSuperAgent">Delete</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.super-agents-page {
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

.sa-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.5rem;
}

.sa-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  transition: all 0.2s;
  cursor: pointer;
}

.sa-card:hover {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 20px rgba(0, 212, 255, 0.1);
}

.sa-card-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.sa-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--accent-cyan, #00d4ff), var(--accent-violet, #8855ff));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.sa-icon svg {
  width: 24px;
  height: 24px;
  color: #fff;
}

.sa-info {
  flex: 1;
  min-width: 0;
}

.sa-info h3 {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0 0 0.5rem 0;
  color: var(--text-primary);
}

.sa-badges {
  display: flex;
  gap: 0.5rem;
}

.badge-backend {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.backend-claude {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.backend-opencode {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.backend-gemini {
  background: var(--accent-amber-dim);
  color: var(--accent-amber);
}

.backend-codex {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.badge-status {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.status-active {
  background: rgba(0, 255, 136, 0.15);
  color: #00ff88;
}

.status-inactive {
  background: rgba(136, 136, 136, 0.15);
  color: #888;
}

.sa-description {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin: 0 0 1rem 0;
  line-height: 1.5;
}

.sa-meta {
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

.sa-actions {
  display: flex;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-subtle);
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
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

.btn-toggle-active {
  background: rgba(0, 255, 136, 0.15);
  color: var(--accent-emerald, #00ff88);
  border: 1px solid rgba(0, 255, 136, 0.3);
}

.btn-toggle-active:hover {
  background: rgba(0, 255, 136, 0.25);
}

.btn-toggle-inactive {
  background: rgba(136, 136, 136, 0.15);
  color: var(--text-tertiary);
  border: 1px solid var(--border-default);
}

.btn-toggle-inactive:hover {
  background: rgba(136, 136, 136, 0.25);
  color: var(--text-secondary);
}
</style>
