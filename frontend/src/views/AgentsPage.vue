<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { Agent } from '../services/api';
import { agentApi, ApiError } from '../services/api';
import PageLayout from '../components/base/PageLayout.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import LoadingState from '../components/base/LoadingState.vue';
import StatusBadge from '../components/base/StatusBadge.vue';
import ListSearchSort from '../components/base/ListSearchSort.vue';
import PaginationBar from '../components/base/PaginationBar.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import { useToast } from '../composables/useToast';
import { useListFilter } from '../composables/useListFilter';
import { usePagination } from '../composables/usePagination';
import { useWebMcpPageTools } from '../webmcp/useWebMcpPageTools';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const showToast = useToast();

const agents = ref<Agent[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const showDeleteConfirm = ref(false);
const agentToDelete = ref<Agent | null>(null);
const runningAgentId = ref<string | null>(null);
const lastRunAgentId = ref<string | null>(null);
const deletingId = ref<string | null>(null);
const togglingId = ref<string | null>(null);

const { searchQuery, sortField, sortOrder, filteredAndSorted, hasActiveFilter, resultCount, totalCount } = useListFilter({
  items: agents,
  searchFields: ['name', 'description', 'role'] as (keyof Agent)[],
  storageKey: 'agents-list-filter',
});

const pagination = usePagination({ defaultPageSize: 25, storageKey: 'agents-pagination' });

const sortOptions = [
  { value: 'name', label: 'Name' },
  { value: 'created_at', label: 'Date Created' },
];

useWebMcpPageTools({
  page: 'AgentsPage',
  domain: 'agents',
  stateGetter: () => ({
    items: agents.value,
    itemCount: agents.value.length,
    isLoading: isLoading.value,
    error: loadError.value,
    searchQuery: searchQuery.value,
    sortField: sortField.value,
    sortOrder: sortOrder.value,
    currentPage: pagination.currentPage.value,
    pageSize: pagination.pageSize.value,
    totalCount: pagination.totalCount.value,
    runningAgentId: runningAgentId.value,
    togglingId: togglingId.value,
  }),
  modalGetter: () => ({
    showCreateModal: false,
    showDeleteConfirm: showDeleteConfirm.value,
  }),
  modalActions: {
    openCreate: () => { router.push({ name: 'agent-create' }); },
    openDelete: (id: string) => {
      const agent = agents.value.find((a: any) => a.id === id);
      if (agent) { agentToDelete.value = agent; showDeleteConfirm.value = true; }
    },
  },
  deps: [agents, searchQuery, sortField, sortOrder],
});

useWebMcpTool({
  name: 'hive_agents_perform_search',
  description: 'Sets the search query on the agents list',
  page: 'AgentsPage',
  inputSchema: {
    type: 'object',
    properties: { query: { type: 'string', description: 'Search text' } },
    required: ['query'],
  },
  execute: async (args: Record<string, unknown>) => {
    searchQuery.value = (args.query as string) || '';
    return { content: [{ type: 'text' as const, text: JSON.stringify({ success: true, searchQuery: searchQuery.value }) }] };
  },
});

useWebMcpTool({
  name: 'hive_agents_perform_sort',
  description: 'Sets the sort field and order on the agents list',
  page: 'AgentsPage',
  inputSchema: {
    type: 'object',
    properties: {
      field: { type: 'string', description: 'Sort field name' },
      order: { type: 'string', enum: ['asc', 'desc'], description: 'Sort order' },
    },
    required: ['field', 'order'],
  },
  execute: async (args: Record<string, unknown>) => {
    sortField.value = (args.field as string) || sortField.value;
    sortOrder.value = (args.order as 'asc' | 'desc') || sortOrder.value;
    return { content: [{ type: 'text' as const, text: JSON.stringify({ success: true, sortField: sortField.value, sortOrder: sortOrder.value }) }] };
  },
});

async function loadAgents() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await agentApi.list({ limit: pagination.pageSize.value, offset: pagination.offset.value });
    agents.value = data.agents || [];
    if (data.total_count != null) pagination.totalCount.value = data.total_count;
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : 'Failed to load agents';
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => { loadAgents(); });
watch([searchQuery, sortField, sortOrder], () => { pagination.resetToFirstPage(); });

async function runAgent(agent: Agent) {
  runningAgentId.value = agent.id;
  lastRunAgentId.value = null;
  try {
    const result = await agentApi.run(agent.id);
    showToast(`Agent "${agent.name}" started (execution: ${result.execution_id})`, 'success');
    lastRunAgentId.value = agent.id;
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to run agent', 'error');
    }
  } finally {
    runningAgentId.value = null;
  }
}

function confirmDelete(agent: Agent) {
  agentToDelete.value = agent;
  showDeleteConfirm.value = true;
}

async function deleteAgent() {
  if (!agentToDelete.value) return;
  deletingId.value = agentToDelete.value.id;
  try {
    await agentApi.delete(agentToDelete.value.id);
    showToast(`Agent "${agentToDelete.value.name}" deleted`, 'success');
    showDeleteConfirm.value = false;
    agentToDelete.value = null;
    await loadAgents();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to delete agent', 'error');
    }
  } finally {
    deletingId.value = null;
  }
}

async function toggleEnabled(agent: Agent) {
  togglingId.value = agent.id;
  try {
    await agentApi.update(agent.id, { enabled: agent.enabled ? 0 : 1 });
    await loadAgents();
  } catch (e) {
    showToast('Failed to update agent', 'error');
  } finally {
    togglingId.value = null;
  }
}

onMounted(() => {
  loadAgents();
});
</script>

<template>
  <PageLayout :breadcrumbs="[{ label: 'Agents' }]">
    <PageHeader title="Agents" subtitle="Manage AI agents with rich context and autonomous capabilities">
      <template #actions>
        <button class="btn btn-primary" @click="router.push({ name: 'agent-create' })">
          + Create Agent
        </button>
      </template>
    </PageHeader>

    <ListSearchSort
      v-if="!isLoading && !loadError && agents.length > 0"
      v-model:searchQuery="searchQuery"
      v-model:sortField="sortField"
      v-model:sortOrder="sortOrder"
      :sort-options="sortOptions"
      :result-count="resultCount"
      :total-count="totalCount"
      placeholder="Search agents..."
    />

    <LoadingState v-if="isLoading" message="Loading agents..." />

    <ErrorState v-else-if="loadError" title="Failed to load agents" :message="loadError" @retry="loadAgents" />

    <EmptyState v-else-if="agents.length === 0" title="No agents yet" description="Create your first AI agent to get started">
      <template #actions>
        <button class="btn btn-primary" @click="router.push({ name: 'agent-create' })">Create Agent</button>
      </template>
    </EmptyState>

    <EmptyState v-else-if="filteredAndSorted.length === 0 && hasActiveFilter" title="No matching agents" description="Try a different search term" />

    <div v-else class="agents-grid">
      <div v-for="agent in filteredAndSorted" :key="agent.id" class="agent-card clickable" :class="{ disabled: !agent.enabled }" @click="router.push({ name: 'agent-design', params: { agentId: agent.id } })">
        <div class="agent-header">
          <div class="agent-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="8" r="4"/>
              <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
            </svg>
          </div>
          <div class="agent-info">
            <h3>{{ agent.name }}</h3>
            <span class="agent-id">{{ agent.id }}</span>
          </div>
          <StatusBadge :label="agent.enabled ? 'Active' : 'Disabled'" :variant="agent.enabled ? 'success' : 'neutral'" />
        </div>

        <p v-if="agent.description" class="agent-description">{{ agent.description }}</p>
        <p v-if="agent.role" class="agent-role">{{ agent.role.substring(0, 100) }}{{ agent.role.length > 100 ? '...' : '' }}</p>

        <div class="agent-meta">
          <div v-if="agent.skills && agent.skills.length > 0" class="meta-item">
            <span class="meta-label">Skills:</span>
            <span class="meta-value">{{ Array.isArray(agent.skills) ? agent.skills.join(', ') : agent.skills }}</span>
          </div>
          <div v-if="agent.goals && Array.isArray(agent.goals) && agent.goals.length > 0" class="meta-item">
            <span class="meta-label">Goals:</span>
            <span class="meta-value">{{ agent.goals.length }} defined</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Backend:</span>
            <span class="meta-value backend-badge" :class="agent.backend_type">{{ agent.backend_type }}</span>
          </div>
        </div>

        <div class="agent-actions" @click.stop>
          <button class="btn btn-small btn-success" @click="runAgent(agent)" :disabled="!agent.enabled || runningAgentId === agent.id">
            <span v-if="runningAgentId === agent.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="currentColor">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            {{ runningAgentId === agent.id ? 'Running...' : 'Run' }}
          </button>
          <button v-if="lastRunAgentId === agent.id" class="btn btn-small btn-view-log" @click="router.push({ name: 'execution-history' })">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
            View Log
          </button>
          <button class="btn btn-small" @click="toggleEnabled(agent)" :disabled="togglingId === agent.id">
            <span v-if="togglingId === agent.id" class="btn-spinner"></span>
            {{ togglingId === agent.id ? '...' : (agent.enabled ? 'Disable' : 'Enable') }}
          </button>
          <button class="btn btn-small btn-danger" @click="confirmDelete(agent)" :disabled="deletingId === agent.id">
            <span v-if="deletingId === agent.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <PaginationBar
      v-if="!isLoading && !loadError && agents.length > 0"
      v-model:currentPage="pagination.currentPage.value"
      v-model:pageSize="pagination.pageSize.value"
      :total-pages="pagination.totalPages.value"
      :page-size-options="pagination.pageSizeOptions"
      :range-start="pagination.rangeStart.value"
      :range-end="pagination.rangeEnd.value"
      :total-count="pagination.totalCount.value"
      :is-first-page="pagination.isFirstPage.value"
      :is-last-page="pagination.isLastPage.value"
    />

    <ConfirmModal
      :open="showDeleteConfirm"
      title="Delete Agent"
      :message="`Are you sure you want to delete \u201C${agentToDelete?.name}\u201D? This action cannot be undone.`"
      confirm-label="Delete"
      cancel-label="Cancel"
      variant="danger"
      @confirm="deleteAgent"
      @cancel="showDeleteConfirm = false"
    />
  </PageLayout>
</template>

<style scoped>
.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}

.agent-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
  transition: border-color 0.2s;
}

.agent-card:hover {
  border-color: var(--border-strong);
}

.agent-card.clickable {
  cursor: pointer;
}

.agent-card.clickable:hover {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 0 1px var(--accent-cyan-dim);
}

.agent-card.disabled {
  opacity: 0.6;
}

.agent-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.agent-icon {
  width: 44px;
  height: 44px;
  background: var(--accent-cyan-dim);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.agent-icon svg {
  width: 24px;
  height: 24px;
  color: var(--accent-cyan);
}

.agent-info {
  flex: 1;
  min-width: 0;
}

.agent-info h3 {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-id {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.agent-description {
  color: var(--text-secondary);
  font-size: 14px;
  margin: 0 0 12px 0;
  line-height: 1.5;
}

.agent-role {
  color: var(--text-tertiary);
  font-size: 13px;
  font-style: italic;
  margin: 0 0 16px 0;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
}

.agent-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.meta-label {
  color: var(--text-tertiary);
}

.meta-value {
  color: var(--text-secondary);
}

.backend-badge {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
}

.backend-badge.claude {
  background: rgba(255, 136, 0, 0.15);
  color: #ff8800;
}

.backend-badge.opencode {
  background: rgba(0, 136, 255, 0.15);
  color: #0088ff;
}

.backend-badge.gemini {
  background: rgba(66, 133, 244, 0.15);
  color: #4285f4;
}

.backend-badge.codex {
  background: rgba(16, 163, 127, 0.15);
  color: #10a37f;
}

.agent-actions {
  display: flex;
  gap: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

.btn-small {
  padding: 6px 12px;
  font-size: 13px;
}

.btn-small svg {
  width: 14px;
  height: 14px;
}

.btn-success {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.btn-success:hover {
  background: rgba(0, 255, 136, 0.25);
}

.btn-view-log {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  animation: fadeIn 0.3s ease;
}

.btn-view-log:hover {
  background: rgba(0, 212, 255, 0.25);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateX(-4px); }
  to { opacity: 1; transform: translateX(0); }
}

.btn-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: btn-spin 0.8s linear infinite;
}

@keyframes btn-spin {
  to { transform: rotate(360deg); }
}
</style>
