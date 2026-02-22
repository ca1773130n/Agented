<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import type { Hook, HookEvent } from '../services/api';
import { hookApi, ApiError } from '../services/api';
import AiStreamingLog from '../components/ai/AiStreamingLog.vue';
import { useStreamingGeneration } from '../composables/useStreamingGeneration';
import PageLayout from '../components/base/PageLayout.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import ListSearchSort from '../components/base/ListSearchSort.vue';
import PaginationBar from '../components/base/PaginationBar.vue';
import SlideOver from '../components/base/SlideOver.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useListFilter } from '../composables/useListFilter';
import { usePagination } from '../composables/usePagination';
import { useWebMcpPageTools } from '../webmcp/useWebMcpPageTools';

const router = useRouter();
const route = useRoute();

const highlightId = computed(() => (route.query.highlightId as string) || null);

const showToast = useToast();

// AI Generate state
const showGenerateModal = ref(false);
const generateDescription = ref('');
const isGenerating = ref(false);
const { log: generateLog, phase: generatePhase, startStream } = useStreamingGeneration();

const hooks = ref<Hook[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const showDeleteConfirm = ref(false);
const hookToDelete = ref<Hook | null>(null);
const deletingId = ref<number | null>(null);
const togglingId = ref<number | null>(null);
const showCreateModal = ref(false);

const createModalRef = ref<HTMLElement | null>(null);
const generateModalRef = ref<HTMLElement | null>(null);
useFocusTrap(createModalRef, showCreateModal);
useFocusTrap(generateModalRef, showGenerateModal);

// Filter state
const filterEvent = ref<HookEvent | ''>('');
const filterProject = ref<string>('');

// Create/edit form
const formData = ref({
  name: '',
  event: 'PreToolUse' as HookEvent,
  description: '',
  content: '',
  enabled: true,
  project_id: '',
});

// SlideOver detail/edit state
const selectedHook = ref<Hook | null>(null);
const editForm = reactive({
  name: '',
  event: '' as HookEvent,
  description: '',
  content: '',
  enabled: true,
  source_path: '',
});
const isSaving = ref(false);

const isDirty = computed(() => {
  if (!selectedHook.value) return false;
  return (
    editForm.name !== selectedHook.value.name ||
    editForm.event !== selectedHook.value.event ||
    editForm.description !== (selectedHook.value.description || '') ||
    editForm.content !== (selectedHook.value.content || '') ||
    editForm.enabled !== !!selectedHook.value.enabled ||
    editForm.source_path !== (selectedHook.value.source_path || '')
  );
});

function editInDesign() {
  if (!selectedHook.value) return;
  const id = selectedHook.value.id;
  closeDetail();
  router.push({ name: 'hook-design', params: { hookId: id } });
}

function openDetail(hook: Hook) {
  selectedHook.value = hook;
  editForm.name = hook.name;
  editForm.event = hook.event;
  editForm.description = hook.description || '';
  editForm.content = hook.content || '';
  editForm.enabled = !!hook.enabled;
  editForm.source_path = hook.source_path || '';
}

// Highlight support — must be after hooks ref and openDetail declaration
function tryHighlight() {
  const id = highlightId.value;
  if (!id || hooks.value.length === 0) return;
  const hook = hooks.value.find(h => h.name === id);
  if (hook) {
    openDetail(hook);
    nextTick(() => {
      const el = document.getElementById(`entity-${hook.id}`) || document.querySelector(`[data-entity-name="${id}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('highlight-pulse');
        setTimeout(() => el.classList.remove('highlight-pulse'), 2000);
      }
    });
  }
}
watch(highlightId, tryHighlight);
watch(() => hooks.value.length, tryHighlight);

function closeDetail() {
  selectedHook.value = null;
}

async function saveDetail() {
  if (!selectedHook.value) return;
  isSaving.value = true;
  try {
    await hookApi.update(selectedHook.value.id, {
      name: editForm.name,
      event: editForm.event,
      description: editForm.description,
      content: editForm.content,
      enabled: editForm.enabled,
      source_path: editForm.source_path || undefined,
    });
    showToast('Hook updated successfully', 'success');
    closeDetail();
    await loadHooks();
  } catch (err: any) {
    showToast(err.message || 'Failed to update hook', 'error');
  } finally {
    isSaving.value = false;
  }
}

const HOOK_EVENTS: HookEvent[] = [
  'PreToolUse',
  'PostToolUse',
  'Stop',
  'SubagentStop',
  'SessionStart',
  'SessionEnd',
  'UserPromptSubmit',
  'PreCompact',
  'Notification',
];

const filteredHooks = computed(() => {
  return hooks.value.filter(h => {
    if (filterEvent.value && h.event !== filterEvent.value) return false;
    if (filterProject.value === 'global' && h.project_id) return false;
    if (filterProject.value && filterProject.value !== 'global' && h.project_id !== filterProject.value) return false;
    return true;
  });
});

const { searchQuery, sortField, sortOrder, filteredAndSorted, resultCount, totalCount } = useListFilter({
  items: filteredHooks,
  searchFields: ['name', 'description'] as (keyof Hook)[],
  storageKey: 'hooks-list-filter',
});

const pagination = usePagination({ defaultPageSize: 25, storageKey: 'hooks-pagination' });

const listSortOptions = [
  { value: 'name', label: 'Name' },
  { value: 'created_at', label: 'Date Created' },
];

useWebMcpPageTools({
  page: 'HooksPage',
  domain: 'hooks',
  stateGetter: () => ({
    items: hooks.value,
    itemCount: hooks.value.length,
    isLoading: isLoading.value,
    error: loadError.value,
    searchQuery: searchQuery.value,
    sortField: sortField.value,
    sortOrder: sortOrder.value,
    currentPage: pagination.currentPage.value,
    pageSize: pagination.pageSize.value,
    totalCount: pagination.totalCount.value,
    filterEvent: filterEvent.value,
    selectedHook: selectedHook.value,
  }),
  modalGetter: () => ({
    showCreateModal: showCreateModal.value,
    showDeleteConfirm: showDeleteConfirm.value,
    formValues: formData.value,
  }),
  modalActions: {
    openCreate: () => { showCreateModal.value = true; },
    openDelete: (id: string) => {
      const hook = hooks.value.find((h: any) => String(h.id) === id);
      if (hook) { hookToDelete.value = hook; showDeleteConfirm.value = true; }
    },
  },
  deps: [hooks, searchQuery, sortField, sortOrder],
});

async function loadHooks() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await hookApi.list(undefined, { limit: pagination.pageSize.value, offset: pagination.offset.value });
    hooks.value = data.hooks || [];
    if (data.total_count != null) pagination.totalCount.value = data.total_count;
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : 'Failed to load hooks';
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => { loadHooks(); });
watch([searchQuery, sortField, sortOrder], () => { pagination.resetToFirstPage(); });
watch([filterEvent, filterProject], () => { pagination.resetToFirstPage(); loadHooks(); });

function confirmDelete(hook: Hook) {
  hookToDelete.value = hook;
  showDeleteConfirm.value = true;
}

async function deleteHook() {
  if (!hookToDelete.value) return;
  deletingId.value = hookToDelete.value.id;
  try {
    await hookApi.delete(hookToDelete.value.id);
    showToast(`Hook "${hookToDelete.value.name}" deleted`, 'success');
    showDeleteConfirm.value = false;
    hookToDelete.value = null;
    await loadHooks();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to delete hook', 'error');
    }
  } finally {
    deletingId.value = null;
  }
}

async function toggleEnabled(hook: Hook) {
  togglingId.value = hook.id;
  try {
    await hookApi.update(hook.id, { enabled: !hook.enabled });
    await loadHooks();
  } catch (e) {
    showToast('Failed to update hook', 'error');
  } finally {
    togglingId.value = null;
  }
}

function openCreateModal() {
  formData.value = {
    name: '',
    event: 'PreToolUse',
    description: '',
    content: '',
    enabled: true,
    project_id: '',
  };
  showCreateModal.value = true;
}

async function createHook() {
  if (!formData.value.name.trim()) {
    showToast('Hook name is required', 'error');
    return;
  }
  try {
    await hookApi.create({
      name: formData.value.name,
      event: formData.value.event,
      description: formData.value.description || undefined,
      content: formData.value.content || undefined,
      enabled: formData.value.enabled,
      project_id: formData.value.project_id || undefined,
    });
    showToast(`Hook "${formData.value.name}" created`, 'success');
    showCreateModal.value = false;
    await loadHooks();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to create hook', 'error');
    }
  }
}

function getEventClass(event: HookEvent): string {
  return 'event-' + event.toLowerCase();
}

async function generateHook() {
  if (!generateDescription.value.trim() || generateDescription.value.trim().length < 10) {
    showToast('Please provide a description of at least 10 characters', 'error');
    return;
  }
  isGenerating.value = true;
  try {
    const result = await startStream<{ config: Record<string, any>; warnings: string[] }>(
      '/admin/hooks/generate/stream',
      { description: generateDescription.value.trim() },
    );
    if (result?.config) {
      formData.value.name = result.config.name || '';
      formData.value.event = result.config.event || 'PreToolUse';
      formData.value.description = result.config.description || '';
      formData.value.content = result.config.content || '';
      formData.value.enabled = result.config.enabled !== false;
      showGenerateModal.value = false;
      showCreateModal.value = true;
      showToast('Hook configuration generated! Review and save.', 'success');
    }
  } catch {
    showToast('Failed to generate hook configuration', 'error');
  } finally {
    isGenerating.value = false;
  }
}

onMounted(() => {
  loadHooks();
});
</script>

<template>
  <PageLayout :breadcrumbs="[{ label: 'Hooks' }]">
    <PageHeader title="Hooks" subtitle="Manage event hooks that trigger on specific Claude Code events">
      <template #actions>
        <button class="btn btn-ai" @click="showGenerateModal = true">
          <span class="ai-badge">AI</span>
          Generate Hook
        </button>
        <button class="btn btn-design" @click="router.push({ name: 'hook-design' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
          Design Hook
        </button>
        <button class="btn btn-primary" @click="openCreateModal">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          New Hook
        </button>
      </template>
    </PageHeader>

    <!-- Filters -->
    <div class="filters-bar">
      <div class="filter-group">
        <label>Event Type:</label>
        <select v-model="filterEvent">
          <option value="">All Events</option>
          <option v-for="event in HOOK_EVENTS" :key="event" :value="event">{{ event }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label>Scope:</label>
        <select v-model="filterProject">
          <option value="">All</option>
          <option value="global">Global Only</option>
        </select>
      </div>
    </div>

    <ListSearchSort
      v-if="!isLoading && !loadError && hooks.length > 0"
      v-model:searchQuery="searchQuery"
      v-model:sortField="sortField"
      v-model:sortOrder="sortOrder"
      :sort-options="listSortOptions"
      :result-count="resultCount"
      :total-count="totalCount"
      placeholder="Search hooks..."
    />

    <LoadingState v-if="isLoading" message="Loading hooks..." />

    <ErrorState
      v-else-if="loadError"
      title="Failed to load hooks"
      :message="loadError"
      @retry="loadHooks"
    />

    <EmptyState
      v-else-if="hooks.length === 0"
      title="No hooks yet"
      description="Create your first hook to trigger actions on Claude Code events"
    >
      <template #actions>
        <button class="btn btn-primary" @click="openCreateModal">Create Hook</button>
      </template>
    </EmptyState>

    <EmptyState
      v-else-if="filteredAndSorted.length === 0"
      title="No matching hooks"
      description="Try a different search term or adjust your filters"
    />

    <div v-else class="hooks-grid">
      <div
        v-for="hook in filteredAndSorted"
        :key="hook.id"
        :id="'entity-' + hook.id"
        :data-entity-name="hook.name"
        class="hook-card clickable"
        :class="{ disabled: !hook.enabled }"
        @click="openDetail(hook)"
      >
        <div class="hook-header">
          <div class="hook-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
            </svg>
          </div>
          <div class="hook-info">
            <h3>{{ hook.name }}</h3>
            <span class="hook-event" :class="getEventClass(hook.event)">
              {{ hook.event }}
            </span>
          </div>
          <div class="hook-status" :class="{ enabled: hook.enabled }">
            {{ hook.enabled ? 'Active' : 'Disabled' }}
          </div>
        </div>

        <p v-if="hook.description" class="hook-description">{{ hook.description }}</p>

        <div class="hook-meta">
          <div class="meta-item">
            <span class="meta-label">Scope:</span>
            <span class="meta-value">{{ hook.project_id ? 'Project' : 'Global' }}</span>
          </div>
          <div v-if="hook.source_path" class="meta-item">
            <span class="meta-label">Source:</span>
            <span class="meta-value source-path">{{ hook.source_path }}</span>
          </div>
          <div v-if="hook.created_at" class="meta-item">
            <span class="meta-label">Created:</span>
            <span class="meta-value">{{ new Date(hook.created_at).toLocaleDateString() }}</span>
          </div>
          <div v-if="hook.updated_at" class="meta-item">
            <span class="meta-label">Updated:</span>
            <span class="meta-value">{{ new Date(hook.updated_at).toLocaleDateString() }}</span>
          </div>
        </div>

        <div class="hook-actions">
          <button class="btn btn-small" @click.stop="toggleEnabled(hook)" :disabled="togglingId === hook.id">
            <span v-if="togglingId === hook.id" class="btn-spinner"></span>
            {{ togglingId === hook.id ? '...' : (hook.enabled ? 'Disable' : 'Enable') }}
          </button>
          <button class="btn btn-small btn-danger" @click.stop="confirmDelete(hook)" :disabled="deletingId === hook.id">
            <span v-if="deletingId === hook.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <PaginationBar
      v-if="!isLoading && !loadError && hooks.length > 0"
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

    <!-- SlideOver Detail/Edit Panel -->
    <SlideOver :open="!!selectedHook" @close="closeDetail" :title="selectedHook?.name || 'Hook Details'" :dirty="isDirty">
      <div class="detail-form">
        <div class="form-group">
          <label>Name</label>
          <input v-model="editForm.name" type="text" placeholder="Hook name" />
        </div>
        <div class="form-group">
          <label>Event</label>
          <select v-model="editForm.event">
            <option v-for="event in HOOK_EVENTS" :key="event" :value="event">{{ event }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>Description</label>
          <textarea v-model="editForm.description" rows="3" placeholder="Hook description"></textarea>
        </div>
        <div class="form-group">
          <label>Content</label>
          <textarea v-model="editForm.content" rows="8" placeholder="Hook content / script" class="code-textarea"></textarea>
        </div>
        <div class="form-group">
          <label class="toggle-label">
            <span>Enabled</span>
            <div class="toggle-switch" :class="{ active: editForm.enabled }" @click="editForm.enabled = !editForm.enabled">
              <div class="toggle-knob"></div>
            </div>
          </label>
        </div>
        <div class="form-group">
          <label>Source Path</label>
          <input v-model="editForm.source_path" type="text" placeholder="/path/to/hook/file" class="source-input" />
          <p class="form-hint">File path for this hook's source (optional)</p>
        </div>
      </div>
      <template #footer>
        <button class="btn btn-design-sm" @click="editInDesign">Edit in Designer</button>
        <button class="btn" @click="closeDetail">Cancel</button>
        <button class="btn btn-primary" @click="saveDetail" :disabled="isSaving || !editForm.name.trim()">
          {{ isSaving ? 'Saving...' : 'Save Changes' }}
        </button>
      </template>
    </SlideOver>

    <ConfirmModal
      :open="showDeleteConfirm"
      title="Delete Hook"
      :message="`Are you sure you want to delete \u201C${hookToDelete?.name}\u201D? This action cannot be undone.`"
      confirm-label="Delete"
      cancel-label="Cancel"
      variant="danger"
      @confirm="deleteHook"
      @cancel="showDeleteConfirm = false"
    />

    <!-- Create Hook Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal" ref="createModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-hook" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal create-modal">
          <h2 id="modal-title-create-hook">Create New Hook</h2>
          <form @submit.prevent="createHook">
            <div class="form-group">
              <label for="hook-name">Name *</label>
              <input id="hook-name" v-model="formData.name" type="text" placeholder="my-hook" required />
            </div>
            <div class="form-group">
              <label for="hook-event">Event Type *</label>
              <select id="hook-event" v-model="formData.event" required>
                <option v-for="event in HOOK_EVENTS" :key="event" :value="event">{{ event }}</option>
              </select>
            </div>
            <div class="form-group">
              <label for="hook-description">Description</label>
              <input id="hook-description" v-model="formData.description" type="text" placeholder="Brief description of what this hook does" />
            </div>
            <div class="form-group">
              <label for="hook-content">Content (Markdown)</label>
              <textarea id="hook-content" v-model="formData.content" rows="6" placeholder="# Hook Content\n\nDescribe what this hook should do..."></textarea>
            </div>
            <div class="form-group checkbox-group">
              <label>
                <input type="checkbox" v-model="formData.enabled" />
                Enabled
              </label>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn" @click="showCreateModal = false">Cancel</button>
              <button type="submit" class="btn btn-primary">Create Hook</button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
    <!-- AI Generate Modal -->
    <Teleport to="body">
      <div v-if="showGenerateModal" ref="generateModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-generate-hook" tabindex="-1" @click.self="showGenerateModal = false" @keydown.escape="showGenerateModal = false">
        <div class="modal generate-modal">
          <h2 id="modal-title-generate-hook">Generate Hook with AI</h2>
          <p>Describe the hook you want to create and AI will generate the configuration.</p>
          <div class="form-group">
            <label for="gen-description">Description</label>
            <textarea
              id="gen-description"
              v-model="generateDescription"
              rows="4"
              placeholder="e.g., A PreToolUse hook that blocks dangerous shell commands like rm -rf / or format disk operations"
              :disabled="isGenerating"
            ></textarea>
          </div>
          <AiStreamingLog
            v-if="isGenerating"
            :log="generateLog"
            :is-streaming="isGenerating"
            :phase="generatePhase || 'Generating hook configuration...'"
            hint="Streaming Claude CLI output"
          />
          <div class="modal-actions">
            <button class="btn" @click="showGenerateModal = false" :disabled="isGenerating">Cancel</button>
            <button class="btn btn-primary" @click="generateHook" :disabled="isGenerating || generateDescription.trim().length < 10">
              {{ isGenerating ? 'Generating...' : 'Generate' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </PageLayout>
</template>

<style scoped>
.hooks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}

.hook-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
  transition: border-color 0.2s;
}

.hook-card:hover {
  border-color: var(--border-strong);
}

.hook-card.clickable {
  cursor: pointer;
}

.hook-card.clickable:hover {
  border-color: var(--accent-primary, #6366f1);
}

.hook-card.disabled {
  opacity: 0.6;
}

.hook-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.hook-icon {
  width: 44px;
  height: 44px;
  background: var(--accent-violet-dim);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.hook-icon svg {
  width: 24px;
  height: 24px;
  color: var(--accent-violet);
}

.hook-info {
  flex: 1;
  min-width: 0;
}

.hook-info h3 {
  margin: 0 0 6px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hook-event {
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
}

.hook-event.event-pretooluse { background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.12)); color: var(--accent-cyan, #00d4ff); }
.hook-event.event-posttooluse { background: var(--accent-emerald-dim, rgba(0, 255, 136, 0.12)); color: var(--accent-emerald, #00ff88); }
.hook-event.event-stop { background: var(--accent-crimson-dim, rgba(255, 51, 102, 0.12)); color: var(--accent-crimson, #ff3366); }
.hook-event.event-subagentstop { background: var(--accent-crimson-dim, rgba(255, 51, 102, 0.12)); color: var(--accent-crimson, #ff3366); }
.hook-event.event-sessionstart { background: var(--accent-violet-dim, rgba(136, 85, 255, 0.12)); color: var(--accent-violet, #8855ff); }
.hook-event.event-sessionend { background: var(--accent-violet-dim, rgba(136, 85, 255, 0.12)); color: var(--accent-violet, #8855ff); }
.hook-event.event-userpromptsubmit { background: var(--accent-amber-dim, rgba(255, 170, 0, 0.12)); color: var(--accent-amber, #ffaa00); }
.hook-event.event-precompact { background: var(--accent-amber-dim, rgba(255, 170, 0, 0.12)); color: var(--accent-amber, #ffaa00); }
.hook-event.event-notification { background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.12)); color: var(--accent-cyan, #00d4ff); }

.hook-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.hook-status.enabled {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.hook-description {
  color: var(--text-secondary);
  font-size: 14px;
  margin: 0 0 16px 0;
  line-height: 1.5;
}

.hook-meta {
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

.meta-value.source-path {
  font-family: var(--font-mono);
  font-size: 11px;
  max-width: 200px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hook-actions {
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

.btn-design-sm {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  color: var(--accent-violet, #8855ff);
  border: 1px solid rgba(136, 85, 255, 0.3);
  font-size: 13px;
  margin-right: auto;
}

.btn-design-sm:hover {
  background: rgba(136, 85, 255, 0.25);
}

.generate-modal {
  max-width: 600px;
}

/* SlideOver detail form */
.detail-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.code-textarea {
  font-family: 'JetBrains Mono', var(--font-mono), monospace;
  font-size: 0.85rem;
}

.source-input {
  font-family: var(--font-mono);
  font-size: 0.85rem;
}

.form-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.toggle-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toggle-switch {
  width: 44px;
  height: 24px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 2px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.toggle-switch.active {
  background: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.toggle-knob {
  display: block;
  width: 18px;
  height: 18px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle-switch.active .toggle-knob {
  transform: translateX(20px);
}
</style>
