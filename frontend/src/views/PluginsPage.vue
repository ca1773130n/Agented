<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import type { Plugin, Team, Marketplace } from '../services/api';
import { pluginApi, teamApi, marketplaceApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import LoadingState from '../components/base/LoadingState.vue';
import StatusBadge from '../components/base/StatusBadge.vue';
import ListSearchSort from '../components/base/ListSearchSort.vue';
import PaginationBar from '../components/base/PaginationBar.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import AiStreamingLog from '../components/ai/AiStreamingLog.vue';
import ExportPluginModal from '../components/plugins/ExportPluginModal.vue';
import ImportPluginModal from '../components/plugins/ImportPluginModal.vue';
import { useStreamingGeneration } from '../composables/useStreamingGeneration';
import { useToast } from '../composables/useToast';
import { useListFilter } from '../composables/useListFilter';
import { usePagination } from '../composables/usePagination';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpPageTools } from '../webmcp/useWebMcpPageTools';

const router = useRouter();
const showToast = useToast();

// AI Generate state
const showGenerateModal = ref(false);
const generateDescription = ref('');
const isGenerating = ref(false);
const { log: generateLog, phase: generatePhase, startStream } = useStreamingGeneration();

const plugins = ref<Plugin[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const showCreateModal = ref(false);
const showDeleteConfirm = ref(false);
const pluginToDelete = ref<Plugin | null>(null);
const deletingId = ref<string | null>(null);

const { searchQuery, sortField, sortOrder, filteredAndSorted, hasActiveFilter, resultCount, totalCount } = useListFilter({
  items: plugins,
  searchFields: ['name', 'description', 'author'] as (keyof Plugin)[],
  storageKey: 'plugins-list-filter',
});

const pagination = usePagination({ defaultPageSize: 25, storageKey: 'plugins-pagination' });

const sortOptions = [
  { value: 'name', label: 'Name' },
  { value: 'created_at', label: 'Date Created' },
];

const newPlugin = ref({ name: '', description: '', version: '1.0.0', status: 'draft', author: '' });

// Modal overlay refs for Escape key handling
const createModalOverlay = ref<HTMLElement | null>(null);
const generateModalOverlay = ref<HTMLElement | null>(null);

useFocusTrap(createModalOverlay, showCreateModal);
useFocusTrap(generateModalOverlay, showGenerateModal);

watch(showCreateModal, (val) => { if (val) nextTick(() => createModalOverlay.value?.focus()); });
watch(showGenerateModal, (val) => { if (val) nextTick(() => generateModalOverlay.value?.focus()); });

// Export/Import state
const showExportModal = ref(false);
const showImportModal = ref(false);
const exportPluginId = ref<string | null>(null);
const teams = ref<Array<{ id: string; name: string }>>([]);
const marketplacesList = ref<Marketplace[]>([]);

useWebMcpPageTools({
  page: 'PluginsPage',
  domain: 'plugins',
  stateGetter: () => ({
    items: plugins.value,
    itemCount: plugins.value.length,
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
    formValues: newPlugin.value,
  }),
  modalActions: {
    openCreate: () => { showCreateModal.value = true; },
    openDelete: (id: string) => {
      const plugin = plugins.value.find((p: any) => p.id === id);
      if (plugin) { pluginToDelete.value = plugin; showDeleteConfirm.value = true; }
    },
  },
  deps: [plugins, searchQuery, sortField, sortOrder],
});

async function loadPlugins() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await pluginApi.list({ limit: pagination.pageSize.value, offset: pagination.offset.value });
    plugins.value = data.plugins || [];
    if (data.total_count != null) pagination.totalCount.value = data.total_count;
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : 'Failed to load plugins';
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => {
  loadPlugins();
});

watch([searchQuery, sortField, sortOrder], () => {
  pagination.resetToFirstPage();
});

async function createPlugin() {
  if (!newPlugin.value.name.trim()) {
    showToast('Plugin name is required', 'error');
    return;
  }
  try {
    await pluginApi.create({
      name: newPlugin.value.name,
      description: newPlugin.value.description || undefined,
      version: newPlugin.value.version,
      status: newPlugin.value.status,
      author: newPlugin.value.author || undefined
    });
    showToast('Plugin created successfully', 'success');
    showCreateModal.value = false;
    newPlugin.value = { name: '', description: '', version: '1.0.0', status: 'draft', author: '' };
    await loadPlugins();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to create plugin', 'error');
    }
  }
}

function confirmDelete(plugin: Plugin) {
  pluginToDelete.value = plugin;
  showDeleteConfirm.value = true;
}

async function deletePlugin() {
  if (!pluginToDelete.value) return;
  deletingId.value = pluginToDelete.value.id;
  try {
    await pluginApi.delete(pluginToDelete.value.id);
    showToast(`Plugin "${pluginToDelete.value.name}" deleted`, 'success');
    showDeleteConfirm.value = false;
    pluginToDelete.value = null;
    await loadPlugins();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to delete plugin', 'error');
    }
  } finally {
    deletingId.value = null;
  }
}

async function generatePlugin() {
  if (!generateDescription.value.trim() || generateDescription.value.trim().length < 10) {
    showToast('Please provide a description of at least 10 characters', 'error');
    return;
  }
  isGenerating.value = true;
  try {
    const result = await startStream<{ config: Record<string, any>; warnings: string[] }>(
      '/admin/plugins/generate/stream',
      { description: generateDescription.value.trim() },
    );
    if (result?.config) {
      newPlugin.value.name = result.config.name || '';
      newPlugin.value.description = result.config.description || '';
      newPlugin.value.version = result.config.version || '1.0.0';
      showGenerateModal.value = false;
      showCreateModal.value = true;
      showToast('Plugin configuration generated! Review and save.', 'success');
    }
  } catch {
    showToast('Failed to generate plugin configuration', 'error');
  } finally {
    isGenerating.value = false;
  }
}

async function loadTeamsAndMarketplaces() {
  try {
    const [teamData, mpData] = await Promise.all([
      teamApi.list(),
      marketplaceApi.list(),
    ]);
    teams.value = (teamData.teams || []).map((t: Team) => ({ id: t.id, name: t.name }));
    marketplacesList.value = mpData.marketplaces || [];
  } catch {
    // Non-blocking: export/import still works if these fail
  }
}

function handleExported() {
  loadPlugins();
}

function handleImported() {
  loadPlugins();
}

onMounted(() => {
  loadPlugins();
  loadTeamsAndMarketplaces();
});
</script>

<template>
  <div class="plugins-page">
    <AppBreadcrumb :items="[{ label: 'Plugins' }]" />
    <PageHeader title="Plugins" subtitle="Create and manage plugins with skills, hooks, and agents">
      <template #actions>
        <button class="btn btn-explore" @click="router.push({ name: 'explore-plugins' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          Explore
        </button>
        <button class="btn btn-export" @click="exportPluginId = null; showExportModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          Export
        </button>
        <button class="btn btn-import" @click="showImportModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Import
        </button>
        <button class="btn btn-ai" @click="showGenerateModal = true">
          <span class="ai-badge">AI</span>
          Generate Plugin
        </button>
        <button class="btn btn-design" @click="router.push({ name: 'plugin-design' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
          Design Plugin
        </button>
        <button class="btn btn-primary" @click="showCreateModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Create Plugin
        </button>
      </template>
    </PageHeader>

    <ListSearchSort
      v-if="!isLoading && !loadError && plugins.length > 0"
      v-model:searchQuery="searchQuery"
      v-model:sortField="sortField"
      v-model:sortOrder="sortOrder"
      :sort-options="sortOptions"
      :result-count="resultCount"
      :total-count="totalCount"
      placeholder="Search plugins..."
    />

    <LoadingState v-if="isLoading" message="Loading plugins..." />

    <ErrorState v-else-if="loadError" title="Failed to load plugins" :message="loadError" @retry="loadPlugins" />

    <EmptyState v-else-if="plugins.length === 0" title="No plugins yet" description="Create your first plugin to extend Agented's capabilities">
      <template #actions>
        <button class="btn btn-primary" @click="showCreateModal = true">Create Your First Plugin</button>
      </template>
    </EmptyState>

    <EmptyState v-else-if="filteredAndSorted.length === 0 && hasActiveFilter" title="No matching plugins" description="Try a different search term" />

    <div v-else class="plugins-grid">
      <div v-for="plugin in filteredAndSorted" :key="plugin.id" class="plugin-card" @click="router.push({ name: 'plugin-detail', params: { pluginId: plugin.id } })">
        <div class="plugin-header">
          <div class="plugin-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
            </svg>
          </div>
          <div class="plugin-info">
            <h3>{{ plugin.name }}</h3>
            <span class="plugin-version">v{{ plugin.version }}</span>
          </div>
          <StatusBadge :label="plugin.status" :variant="plugin.status === 'published' ? 'success' : plugin.status === 'draft' ? 'warning' : 'neutral'" />
        </div>

        <p v-if="plugin.description" class="plugin-description">{{ plugin.description }}</p>

        <div class="plugin-meta">
          <div v-if="plugin.author" class="meta-item">
            <span class="meta-label">Author:</span>
            <span class="meta-value">{{ plugin.author }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Components:</span>
            <span class="meta-value">{{ plugin.component_count }}</span>
          </div>
        </div>

        <div class="plugin-actions">
          <button class="btn btn-small btn-outline" @click.stop="exportPluginId = plugin.id; showExportModal = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            Export
          </button>
          <button class="btn btn-small btn-danger" @click.stop="confirmDelete(plugin)" :disabled="deletingId === plugin.id">
            <span v-if="deletingId === plugin.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            {{ deletingId === plugin.id ? 'Deleting...' : 'Delete' }}
          </button>
        </div>
      </div>
    </div>

    <PaginationBar
      v-if="!isLoading && !loadError && plugins.length > 0"
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
      <div v-if="showCreateModal" ref="createModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-plugin" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-create-plugin">Create Plugin</h2>
            <button class="modal-close" @click="showCreateModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Plugin Name *</label>
              <input v-model="newPlugin.name" type="text" placeholder="e.g., security-scanner" />
            </div>
            <div class="form-group">
              <label>Description</label>
              <textarea v-model="newPlugin.description" placeholder="Describe the plugin..."></textarea>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>Version</label>
                <input v-model="newPlugin.version" type="text" placeholder="1.0.0" />
              </div>
              <div class="form-group">
                <label>Status</label>
                <select v-model="newPlugin.status">
                  <option value="draft">Draft</option>
                  <option value="published">Published</option>
                  <option value="deprecated">Deprecated</option>
                </select>
              </div>
            </div>
            <div class="form-group">
              <label>Author</label>
              <input v-model="newPlugin.author" type="text" placeholder="Your name or org" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCreateModal = false">Cancel</button>
            <button class="btn btn-primary" @click="createPlugin">Create Plugin</button>
          </div>
        </div>
      </div>
    </Teleport>

    <ConfirmModal
      :open="showDeleteConfirm"
      title="Delete Plugin"
      :message="`Are you sure you want to delete \u201C${pluginToDelete?.name}\u201D? This action cannot be undone.`"
      confirm-label="Delete"
      cancel-label="Cancel"
      variant="danger"
      @confirm="deletePlugin"
      @cancel="showDeleteConfirm = false"
    />

    <!-- AI Generate Modal -->
    <Teleport to="body">
      <div v-if="showGenerateModal" ref="generateModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-generate-plugin" tabindex="-1" @click.self="showGenerateModal = false" @keydown.escape="showGenerateModal = false">
        <div class="modal generate-modal">
          <div class="modal-header">
            <h2 id="modal-title-generate-plugin">Generate Plugin with AI</h2>
            <button class="modal-close" @click="showGenerateModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <p>Describe the plugin you want to create and AI will generate the configuration with components.</p>
            <div class="form-group">
              <label>Description</label>
              <textarea
                v-model="generateDescription"
                rows="4"
                placeholder="e.g., A code quality plugin with a pre-commit hook that runs linting, a slash command for generating documentation, and a validation rule for test coverage"
                :disabled="isGenerating"
              ></textarea>
            </div>
            <AiStreamingLog
              v-if="isGenerating"
              :log="generateLog"
              :is-streaming="isGenerating"
              :phase="generatePhase || 'Generating plugin configuration...'"
              hint="Streaming Claude CLI output"
            />
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showGenerateModal = false" :disabled="isGenerating">Cancel</button>
            <button class="btn btn-primary" @click="generatePlugin" :disabled="isGenerating || generateDescription.trim().length < 10">
              {{ isGenerating ? 'Generating...' : 'Generate' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Export Modal -->
    <ExportPluginModal
      :show="showExportModal"
      :teams="teams"
      :plugin-id="exportPluginId"
      @close="showExportModal = false; exportPluginId = null"
      @exported="handleExported"
    />

    <!-- Import Modal -->
    <ImportPluginModal
      :show="showImportModal"
      :marketplaces="marketplacesList"
      @close="showImportModal = false"
      @imported="handleImported"
    />
  </div>
</template>

<style scoped>
.plugins-page {
}

.btn-explore {
  background: rgba(0, 255, 136, 0.15);
  color: #00ff88;
  border: 1px solid rgba(0, 255, 136, 0.3);
}

.btn-explore:hover {
  background: rgba(0, 255, 136, 0.25);
  border-color: rgba(0, 255, 136, 0.5);
}

.btn-explore svg {
  width: 16px;
  height: 16px;
}

.btn-design {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  color: var(--accent-violet, #8855ff);
  border: 1px solid rgba(136, 85, 255, 0.3);
}

.btn-design:hover {
  background: rgba(136, 85, 255, 0.25);
}

.btn-design svg {
  width: 16px;
  height: 16px;
}

.btn-export {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan, #00d4ff);
  border: 1px solid rgba(0, 212, 255, 0.3);
}

.btn-export:hover {
  background: rgba(0, 212, 255, 0.25);
  border-color: rgba(0, 212, 255, 0.5);
}

.btn-import {
  background: rgba(0, 255, 136, 0.15);
  color: #00ff88;
  border: 1px solid rgba(0, 255, 136, 0.3);
}

.btn-import:hover {
  background: rgba(0, 255, 136, 0.25);
  border-color: rgba(0, 255, 136, 0.5);
}

.btn-outline {
  background: transparent;
  color: var(--accent-cyan, #00d4ff);
  border: 1px solid rgba(0, 212, 255, 0.3);
}

.btn-outline:hover {
  background: rgba(0, 212, 255, 0.15);
}

.generate-modal {
  max-width: 600px;
}

.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-default);
}

.btn-danger {
  background: rgba(255, 77, 77, 0.2);
  color: #ff4d4d;
  border: 1px solid rgba(255, 77, 77, 0.3);
}

.btn-small { padding: 0.5rem 0.75rem; font-size: 0.85rem; }
.btn-small svg { width: 14px; height: 14px; }

.btn-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.plugins-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.5rem;
}

.plugin-card {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  transition: all 0.2s;
  cursor: pointer;
}

.plugin-card:hover {
  border-color: var(--accent-violet, #8855ff);
  box-shadow: 0 0 20px rgba(136, 85, 255, 0.1);
}

.plugin-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.plugin-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--accent-violet, #8855ff), var(--accent-cyan, #00d4ff));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.plugin-icon svg {
  width: 24px;
  height: 24px;
  color: #fff;
}

.plugin-info { flex: 1; min-width: 0; }
.plugin-info h3 { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.25rem; }
.plugin-version { font-size: 0.75rem; color: var(--text-secondary, #888); font-family: monospace; }

.plugin-description {
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
  margin-bottom: 1rem;
  line-height: 1.5;
}

.plugin-meta {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 1rem;
}

.meta-item { font-size: 0.85rem; }
.meta-label { color: var(--text-secondary, #888); margin-right: 0.5rem; }
.meta-value { color: var(--text-primary, #fff); }

.plugin-actions {
  display: flex;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-default);
}

/* Modal styles */

.modal-large { max-width: 700px; }
.modal-small { max-width: 400px; }

.modal-header h2 { font-size: 1.25rem; font-weight: 600; }

.header-with-version {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.version-badge {
  font-size: 0.75rem;
  font-family: monospace;
  color: var(--text-secondary, #888);
  background: var(--bg-tertiary, #1a1a24);
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-secondary, #888);
  cursor: pointer;
}

.form-row { display: flex; gap: 1rem; }

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.warning-text { color: #ff4d4d; font-size: 0.9rem; margin-top: 0.5rem; }

.section-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 1.5rem 0 1rem;
  color: var(--text-secondary, #888);
}

.detail-description { color: var(--text-secondary, #888); line-height: 1.6; }

.detail-meta {
  display: flex;
  gap: 1rem;
  margin-top: 1rem;
  align-items: center;
}

.author-tag {
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
}

.components-list { display: flex; flex-direction: column; gap: 0.5rem; }

.component-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: var(--bg-tertiary, #1a1a24);
  border-radius: 8px;
}

.component-icon {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: var(--bg-secondary, #12121a);
  display: flex;
  align-items: center;
  justify-content: center;
}

.component-icon svg {
  width: 16px;
  height: 16px;
  color: var(--accent-violet, #8855ff);
}

.component-info { flex: 1; }
.component-name { display: block; font-weight: 500; }
.component-type {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary, #888);
  text-transform: uppercase;
}

.no-components { color: var(--text-secondary, #888); text-align: center; padding: 2rem; }
</style>
