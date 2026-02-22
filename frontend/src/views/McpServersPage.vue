<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import type { McpServer } from '../services/api';
import { mcpServerApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import LoadingState from '../components/base/LoadingState.vue';
import ListSearchSort from '../components/base/ListSearchSort.vue';
import PaginationBar from '../components/base/PaginationBar.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import { useToast } from '../composables/useToast';
import { useListFilter } from '../composables/useListFilter';
import { usePagination } from '../composables/usePagination';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpPageTools } from '../webmcp/useWebMcpPageTools';

const router = useRouter();

const showToast = useToast();

const servers = ref<McpServer[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const showCreateModal = ref(false);
const showDeleteConfirm = ref(false);
const serverToDelete = ref<McpServer | null>(null);
const deletingId = ref<string | null>(null);

const { searchQuery, sortField, sortOrder, filteredAndSorted, hasActiveFilter, resultCount, totalCount } = useListFilter({
  items: servers,
  searchFields: ['name', 'description', 'display_name'] as (keyof McpServer)[],
  storageKey: 'mcp-list-filter',
  sortAccessors: {
    name: (item: McpServer) => item.display_name || item.name,
  },
});

const pagination = usePagination({ defaultPageSize: 25, storageKey: 'mcp-pagination' });

const sortOptions = [
  { value: 'name', label: 'Name' },
  { value: 'created_at', label: 'Date Created' },
];

const newServer = ref({
  name: '',
  server_type: 'stdio',
  command: '',
  args: '',
  url: '',
  description: '',
});

// Modal overlay refs for Escape key handling
const createModalOverlay = ref<HTMLElement | null>(null);

useFocusTrap(createModalOverlay, showCreateModal);
watch(showCreateModal, (val) => { if (val) nextTick(() => createModalOverlay.value?.focus()); });

useWebMcpPageTools({
  page: 'McpServersPage',
  domain: 'mcp_servers',
  stateGetter: () => ({
    items: servers.value,
    itemCount: servers.value.length,
    isLoading: isLoading.value,
    error: loadError.value,
    searchQuery: searchQuery.value,
    sortField: sortField.value,
    sortOrder: sortOrder.value,
    currentPage: pagination.currentPage.value,
    pageSize: pagination.pageSize.value,
    totalCount: pagination.totalCount.value,
  }),
  modalGetter: () => ({
    showCreateModal: showCreateModal.value,
    showDeleteConfirm: showDeleteConfirm.value,
    formValues: newServer.value,
  }),
  modalActions: {
    openCreate: () => { showCreateModal.value = true; },
    openDelete: (id: string) => {
      const server = servers.value.find((s: any) => s.id === id);
      if (server) { serverToDelete.value = server; showDeleteConfirm.value = true; }
    },
  },
  deps: [servers, searchQuery, sortField, sortOrder],
});

async function loadServers() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await mcpServerApi.list({ limit: pagination.pageSize.value, offset: pagination.offset.value });
    servers.value = data.servers || [];
    if (data.total_count != null) pagination.totalCount.value = data.total_count;
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : 'Failed to load MCP servers';
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => {
  loadServers();
});

watch([searchQuery, sortField, sortOrder], () => {
  pagination.resetToFirstPage();
});

async function createServer() {
  if (!newServer.value.name.trim()) {
    showToast('Server name is required', 'error');
    return;
  }
  try {
    await mcpServerApi.create({
      name: newServer.value.name,
      server_type: newServer.value.server_type,
      command: newServer.value.command || undefined,
      args: newServer.value.args || undefined,
      url: newServer.value.url || undefined,
      description: newServer.value.description || undefined,
    } as Partial<McpServer>);
    showToast('MCP server created successfully', 'success');
    showCreateModal.value = false;
    newServer.value = { name: '', server_type: 'stdio', command: '', args: '', url: '', description: '' };
    await loadServers();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to create MCP server', 'error');
    }
  }
}

function confirmDelete(server: McpServer) {
  serverToDelete.value = server;
  showDeleteConfirm.value = true;
}

async function deleteServer() {
  if (!serverToDelete.value) return;
  deletingId.value = serverToDelete.value.id;
  try {
    await mcpServerApi.delete(serverToDelete.value.id);
    showToast(`Server "${serverToDelete.value.name}" deleted`, 'success');
    showDeleteConfirm.value = false;
    serverToDelete.value = null;
    await loadServers();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to delete MCP server', 'error');
    }
  } finally {
    deletingId.value = null;
  }
}

function getServerTypeBadgeClass(serverType: string) {
  switch (serverType) {
    case 'stdio': return 'type-stdio';
    case 'sse': return 'type-sse';
    case 'http': return 'type-http';
    default: return '';
  }
}

onMounted(() => {
  loadServers();
});
</script>

<template>
  <div class="mcp-servers-page">
    <AppBreadcrumb :items="[{ label: 'MCP Servers' }]" />
    <PageHeader title="MCP Servers" subtitle="Manage Model Context Protocol server configurations">
      <template #actions>
        <button class="btn btn-primary" @click="showCreateModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Create Server
        </button>
      </template>
    </PageHeader>

    <ListSearchSort
      v-if="!isLoading && !loadError && servers.length > 0"
      v-model:searchQuery="searchQuery"
      v-model:sortField="sortField"
      v-model:sortOrder="sortOrder"
      :sort-options="sortOptions"
      :result-count="resultCount"
      :total-count="totalCount"
      placeholder="Search MCP servers..."
    />

    <LoadingState v-if="isLoading" message="Loading MCP servers..." />

    <ErrorState
      v-else-if="loadError"
      title="Failed to load MCP servers"
      :message="loadError"
      @retry="loadServers"
    />

    <EmptyState
      v-else-if="servers.length === 0"
      title="No MCP servers yet"
      description="Create your first server or explore the marketplace."
    >
      <template #actions>
        <button class="btn btn-primary" @click="showCreateModal = true">Create Your First Server</button>
      </template>
    </EmptyState>

    <EmptyState
      v-else-if="filteredAndSorted.length === 0 && hasActiveFilter"
      title="No matching MCP servers"
      description="Try a different search term"
    />

    <div v-else class="servers-grid">
      <div
        v-for="server in filteredAndSorted"
        :key="server.id"
        class="server-card"
        @click="router.push({ name: 'mcp-server-detail', params: { mcpServerId: server.id } })"
      >
        <div class="server-header">
          <div class="server-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="2" y="2" width="20" height="8" rx="2"/>
              <rect x="2" y="14" width="20" height="8" rx="2"/>
              <circle cx="6" cy="6" r="1" fill="currentColor"/>
              <circle cx="6" cy="18" r="1" fill="currentColor"/>
            </svg>
          </div>
          <div class="server-info">
            <h3>{{ server.display_name || server.name }}</h3>
            <span class="server-name-sub" v-if="server.display_name">{{ server.name }}</span>
          </div>
          <div class="server-badges">
            <span :class="['type-badge', getServerTypeBadgeClass(server.server_type)]">{{ server.server_type }}</span>
            <span v-if="server.is_preset" class="preset-badge">Preset</span>
          </div>
        </div>

        <p v-if="server.description" class="server-description">{{ server.description }}</p>
        <p v-else class="server-description muted">No description</p>

        <div class="server-meta">
          <div v-if="server.command" class="meta-item">
            <span class="meta-label">Command:</span>
            <span class="meta-value mono">{{ server.command }}</span>
          </div>
          <div v-if="server.url" class="meta-item">
            <span class="meta-label">URL:</span>
            <span class="meta-value mono">{{ server.url }}</span>
          </div>
        </div>

        <div class="server-actions" v-if="!server.is_preset">
          <button class="btn btn-small btn-danger" @click.stop="confirmDelete(server)" :disabled="deletingId === server.id">
            <span v-if="deletingId === server.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            {{ deletingId === server.id ? 'Deleting...' : 'Delete' }}
          </button>
        </div>
      </div>
    </div>

    <PaginationBar
      v-if="!isLoading && !loadError && servers.length > 0"
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

    <!-- Create Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal" ref="createModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-mcp" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-create-mcp">Create MCP Server</h2>
            <button class="modal-close" @click="showCreateModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Server Name *</label>
              <input v-model="newServer.name" type="text" placeholder="e.g., my-mcp-server" />
            </div>
            <div class="form-group">
              <label>Server Type</label>
              <select v-model="newServer.server_type">
                <option value="stdio">stdio</option>
                <option value="sse">sse</option>
                <option value="http">http</option>
              </select>
            </div>
            <div v-if="newServer.server_type === 'stdio'" class="form-group">
              <label>Command</label>
              <input v-model="newServer.command" type="text" placeholder="e.g., npx -y @modelcontextprotocol/server-filesystem" />
            </div>
            <div v-if="newServer.server_type === 'stdio'" class="form-group">
              <label>Args</label>
              <input v-model="newServer.args" type="text" placeholder="e.g., /path/to/dir" />
            </div>
            <div v-if="newServer.server_type !== 'stdio'" class="form-group">
              <label>URL</label>
              <input v-model="newServer.url" type="text" placeholder="e.g., http://localhost:3001/sse" />
            </div>
            <div class="form-group">
              <label>Description</label>
              <textarea v-model="newServer.description" placeholder="Describe the server..."></textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn" @click="showCreateModal = false">Cancel</button>
            <button class="btn btn-primary" @click="createServer">Create Server</button>
          </div>
        </div>
      </div>
    </Teleport>

    <ConfirmModal
      :open="showDeleteConfirm"
      title="Delete MCP Server"
      :message="`Are you sure you want to delete \u201C${serverToDelete?.name}\u201D? This action cannot be undone.`"
      confirm-label="Delete"
      cancel-label="Cancel"
      variant="danger"
      @confirm="deleteServer"
      @cancel="showDeleteConfirm = false"
    />
  </div>
</template>

<style scoped>
.mcp-servers-page {
}

.servers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.5rem;
}

.server-card {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  transition: all 0.2s;
  cursor: pointer;
}

.server-card:hover {
  border-color: var(--accent-cyan, #00d4ff);
  box-shadow: 0 0 20px rgba(0, 212, 255, 0.1);
}

.server-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.server-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--accent-cyan, #00d4ff), var(--accent-violet, #8855ff));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.server-icon svg {
  width: 24px;
  height: 24px;
  color: #fff;
}

.server-info {
  flex: 1;
  min-width: 0;
}

.server-info h3 {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.server-name-sub {
  font-size: 0.75rem;
  color: var(--text-tertiary, #606070);
  font-family: var(--font-mono);
}

.server-badges {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

.type-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
}

.type-stdio { background: rgba(0, 212, 255, 0.2); color: var(--accent-cyan, #00d4ff); }
.type-sse { background: rgba(136, 85, 255, 0.2); color: var(--accent-violet, #8855ff); }
.type-http { background: rgba(0, 255, 136, 0.2); color: var(--accent-emerald, #00ff88); }

.preset-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 500;
  background: rgba(255, 170, 0, 0.2);
  color: var(--accent-amber, #ffaa00);
}

.server-description {
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
  margin-bottom: 1rem;
  line-height: 1.5;
}

.server-description.muted {
  color: var(--text-tertiary, #606070);
  font-style: italic;
}

.server-meta {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.meta-item {
  font-size: 0.85rem;
  display: flex;
  gap: 0.5rem;
}

.meta-label {
  color: var(--text-tertiary, #606070);
}

.meta-value {
  color: var(--text-primary, #fff);
}

.meta-value.mono {
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.server-actions {
  display: flex;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-subtle);
}

.btn-small {
  padding: 0.5rem 0.75rem;
  font-size: 0.85rem;
}

.btn-small svg {
  width: 14px;
  height: 14px;
}

.btn-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.modal-small {
  max-width: 400px;
}

.warning-text {
  color: #ff4d4d;
  font-size: 0.9rem;
  margin-top: 0.5rem;
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-secondary, #888);
  cursor: pointer;
}
</style>
