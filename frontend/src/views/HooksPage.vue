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
import { useWebMcpPageTools } from '../composables/useWebMcpPageTools';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
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
    showToast(t('hooks.toast.updated'), 'success');
    closeDetail();
    await loadHooks();
  } catch (err: unknown) {
    showToast(err instanceof Error ? err.message : t('hooks.toast.updateFailed'), 'error');
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

// Client-side scope filters (event / project) the server list does not handle.
// Search + sort are now server-driven (see loadHooks); these only narrow the
// already-fetched, server-filtered page.
const displayHooks = computed(() => {
  return hooks.value.filter(h => {
    if (filterEvent.value && h.event !== filterEvent.value) return false;
    if (filterProject.value === 'global' && h.project_id) return false;
    if (filterProject.value && filterProject.value !== 'global' && h.project_id !== filterProject.value) return false;
    return true;
  });
});

// useListFilter still owns the search/sort UI state + sessionStorage persistence;
// we drive the SERVER call with these refs instead of its client-side filteredAndSorted.
const { searchQuery, sortField, sortOrder } = useListFilter({
  items: hooks,
  searchFields: ['name', 'description'] as (keyof Hook)[],
  storageKey: 'hooks-list-filter',
});

const pagination = usePagination({ defaultPageSize: 25, storageKey: 'hooks-pagination' });

const listSortOptions = computed(() => [
  { value: 'name', label: t('hooks.sort.name') },
  { value: 'created_at', label: t('hooks.sort.dateCreated') },
]);

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
      const hook = hooks.value.find((h) => String(h.id) === id);
      if (hook) { hookToDelete.value = hook; showDeleteConfirm.value = true; }
    },
  },
  deps: [hooks, searchQuery, sortField, sortOrder],
});

async function loadHooks() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await hookApi.list(undefined, {
      limit: pagination.pageSize.value,
      offset: pagination.offset.value,
      search: searchQuery.value.trim() || undefined,
      sort: sortField.value as 'name' | 'created_at' | 'updated_at',
      order: sortOrder.value,
    });
    hooks.value = data.hooks || [];
    if (data.total_count != null) pagination.totalCount.value = data.total_count;
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : t('hooks.toast.loadFailed');
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

// Debounce search so we don't fire a request per keystroke (~300ms).
let searchDebounce: ReturnType<typeof setTimeout> | undefined;
watch(searchQuery, () => {
  if (searchDebounce) clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    pagination.resetToFirstPage();
    loadHooks();
  }, 300);
});

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => { loadHooks(); });
// Sort changes refetch immediately (reset to page 1).
watch([sortField, sortOrder], () => { pagination.resetToFirstPage(); loadHooks(); });
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
    showToast(t('hooks.toast.deleted', { name: hookToDelete.value.name }), 'success');
    showDeleteConfirm.value = false;
    hookToDelete.value = null;
    await loadHooks();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(t('hooks.toast.deleteFailed'), 'error');
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
    showToast(t('hooks.toast.updateFailed'), 'error');
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

const isCreating = ref(false);
async function createHook() {
  if (isCreating.value) return;
  if (!formData.value.name.trim()) {
    showToast(t('hooks.toast.nameRequired'), 'error');
    return;
  }
  isCreating.value = true;
  try {
    await hookApi.create({
      name: formData.value.name,
      event: formData.value.event,
      description: formData.value.description || undefined,
      content: formData.value.content || undefined,
      enabled: formData.value.enabled,
      project_id: formData.value.project_id || undefined,
    });
    showToast(t('hooks.toast.created', { name: formData.value.name }), 'success');
    showCreateModal.value = false;
    await loadHooks();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(t('hooks.toast.createFailed'), 'error');
    }
  } finally {
    isCreating.value = false;
  }
}

function getEventClass(event: HookEvent): string {
  return 'event-' + event.toLowerCase();
}

async function generateHook() {
  if (!generateDescription.value.trim() || generateDescription.value.trim().length < 10) {
    showToast(t('hooks.toast.descriptionTooShort'), 'error');
    return;
  }
  isGenerating.value = true;
  try {
    const result = await startStream<{ config: Record<string, string>; warnings: string[] }>(
      '/admin/hooks/generate/stream',
      { description: generateDescription.value.trim() },
    );
    if (result?.config) {
      formData.value.name = result.config.name || '';
      formData.value.event = (result.config.event || 'PreToolUse') as HookEvent;
      formData.value.description = result.config.description || '';
      formData.value.content = result.config.content || '';
      formData.value.enabled = result.config.enabled !== 'false';
      showGenerateModal.value = false;
      showCreateModal.value = true;
      showToast(t('hooks.toast.generated'), 'success');
    }
  } catch {
    showToast(t('hooks.toast.generateFailed'), 'error');
  } finally {
    isGenerating.value = false;
  }
}

onMounted(() => {
  loadHooks();
});
</script>

<template>
  <PageLayout >
    <PageHeader :title="t('hooks.title')" :subtitle="t('hooks.subtitle')">
      <template #actions>
        <button class="btn btn-ai" @click="showGenerateModal = true">
          <span class="ai-badge">AI</span>
          {{ t('hooks.generateHook') }}
        </button>
        <button class="btn btn-design" @click="router.push({ name: 'hook-design' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
          </svg>
          {{ t('hooks.designHook') }}
        </button>
        <button class="btn btn-primary" @click="openCreateModal">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          {{ t('hooks.newHook') }}
        </button>
      </template>
    </PageHeader>

    <!-- Filters -->
    <div class="filters-bar">
      <div class="filter-group">
        <label>{{ t('hooks.filters.eventType') }}</label>
        <select v-model="filterEvent">
          <option value="">{{ t('hooks.filters.allEvents') }}</option>
          <option v-for="event in HOOK_EVENTS" :key="event" :value="event">{{ event }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label>{{ t('hooks.filters.scope') }}</label>
        <select v-model="filterProject">
          <option value="">{{ t('hooks.filters.all') }}</option>
          <option value="global">{{ t('hooks.filters.globalOnly') }}</option>
        </select>
      </div>
    </div>

    <ListSearchSort
      v-if="!isLoading && !loadError && hooks.length > 0"
      v-model:searchQuery="searchQuery"
      v-model:sortField="sortField"
      v-model:sortOrder="sortOrder"
      :sort-options="listSortOptions"
      :result-count="displayHooks.length"
      :total-count="pagination.totalCount.value"
      :placeholder="t('hooks.searchPlaceholder')"
    />

    <LoadingState v-if="isLoading" :message="t('hooks.loading')" />

    <ErrorState
      v-else-if="loadError"
      :title="t('hooks.loadErrorTitle')"
      :message="loadError"
      @retry="loadHooks"
    />

    <EmptyState
      v-else-if="hooks.length === 0"
      :title="t('hooks.empty.title')"
      :description="t('hooks.empty.description')"
    >
      <template #actions>
        <button class="btn btn-primary" @click="openCreateModal">{{ t('hooks.createHook') }}</button>
      </template>
    </EmptyState>

    <EmptyState
      v-else-if="displayHooks.length === 0"
      :title="t('hooks.noMatch.title')"
      :description="t('hooks.noMatch.description')"
    />

    <div v-else class="hooks-grid">
      <div
        v-for="hook in displayHooks"
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
            {{ hook.enabled ? t('hooks.status.active') : t('hooks.status.disabled') }}
          </div>
        </div>

        <p v-if="hook.description" class="hook-description">{{ hook.description }}</p>

        <div class="hook-meta">
          <div class="meta-item">
            <span class="meta-label">{{ t('hooks.meta.scope') }}</span>
            <span class="meta-value">{{ hook.project_id ? t('hooks.scope.project') : t('hooks.scope.global') }}</span>
          </div>
          <div v-if="hook.source_path" class="meta-item">
            <span class="meta-label">{{ t('hooks.meta.source') }}</span>
            <span class="meta-value source-path">{{ hook.source_path }}</span>
          </div>
          <div v-if="hook.created_at" class="meta-item">
            <span class="meta-label">{{ t('hooks.meta.created') }}</span>
            <span class="meta-value">{{ new Date(hook.created_at).toLocaleDateString() }}</span>
          </div>
          <div v-if="hook.updated_at" class="meta-item">
            <span class="meta-label">{{ t('hooks.meta.updated') }}</span>
            <span class="meta-value">{{ new Date(hook.updated_at).toLocaleDateString() }}</span>
          </div>
        </div>

        <div class="hook-actions">
          <button class="btn btn-small" @click.stop="toggleEnabled(hook)" :disabled="togglingId === hook.id">
            <span v-if="togglingId === hook.id" class="btn-spinner"></span>
            {{ togglingId === hook.id ? '...' : (hook.enabled ? t('hooks.disable') : t('hooks.enable')) }}
          </button>
          <button class="btn btn-small btn-danger" :aria-label="t('common.delete')" @click.stop="confirmDelete(hook)" :disabled="deletingId === hook.id">
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
    <SlideOver :open="!!selectedHook" @close="closeDetail" :title="selectedHook?.name || t('hooks.detailTitle')" :dirty="isDirty">
      <div class="detail-form">
        <div class="form-group">
          <label>{{ t('hooks.form.name') }}</label>
          <input v-model="editForm.name" type="text" :placeholder="t('hooks.form.namePlaceholder')" />
        </div>
        <div class="form-group">
          <label>{{ t('hooks.form.event') }}</label>
          <select v-model="editForm.event">
            <option v-for="event in HOOK_EVENTS" :key="event" :value="event">{{ event }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>{{ t('hooks.form.description') }}</label>
          <textarea v-model="editForm.description" rows="3" :placeholder="t('hooks.form.descriptionPlaceholder')"></textarea>
        </div>
        <div class="form-group">
          <label>{{ t('hooks.form.content') }}</label>
          <textarea v-model="editForm.content" rows="8" :placeholder="t('hooks.form.contentScriptPlaceholder')" class="code-textarea"></textarea>
        </div>
        <div class="form-group">
          <label class="toggle-label">
            <span>{{ t('hooks.form.enabled') }}</span>
            <div
              class="toggle-switch"
              :class="{ active: editForm.enabled }"
              role="switch"
              :aria-checked="editForm.enabled"
              :aria-label="t('hooks.form.enabled')"
              tabindex="0"
              @click="editForm.enabled = !editForm.enabled"
              @keydown.enter.prevent="editForm.enabled = !editForm.enabled"
              @keydown.space.prevent="editForm.enabled = !editForm.enabled"
            >
              <div class="toggle-knob"></div>
            </div>
          </label>
        </div>
        <div class="form-group">
          <label>{{ t('hooks.form.sourcePath') }}</label>
          <input v-model="editForm.source_path" type="text" :placeholder="t('hooks.form.sourcePathPlaceholder')" class="source-input" />
          <p class="form-hint">{{ t('hooks.form.sourcePathHint') }}</p>
        </div>
      </div>
      <template #footer>
        <button class="btn btn-design-sm" @click="editInDesign">{{ t('hooks.editInDesigner') }}</button>
        <button class="btn" @click="closeDetail">{{ t('common.cancel') }}</button>
        <button class="btn btn-primary" @click="saveDetail" :disabled="isSaving || !editForm.name.trim()">
          {{ isSaving ? t('hooks.saving') : t('hooks.saveChanges') }}
        </button>
      </template>
    </SlideOver>

    <ConfirmModal
      :open="showDeleteConfirm"
      :title="t('hooks.deleteModal.title')"
      :message="t('hooks.deleteModal.message', { name: hookToDelete?.name })"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      variant="danger"
      @confirm="deleteHook"
      @cancel="showDeleteConfirm = false"
    />

    <!-- Create Hook Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal" ref="createModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-hook" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal create-modal">
          <h2 id="modal-title-create-hook">{{ t('hooks.createModal.title') }}</h2>
          <form @submit.prevent="createHook">
            <div class="form-group">
              <label for="hook-name">{{ t('hooks.form.nameRequired') }}</label>
              <input id="hook-name" v-model="formData.name" type="text" placeholder="my-hook" required />
            </div>
            <div class="form-group">
              <label for="hook-event">{{ t('hooks.form.eventTypeRequired') }}</label>
              <select id="hook-event" v-model="formData.event" required>
                <option v-for="event in HOOK_EVENTS" :key="event" :value="event">{{ event }}</option>
              </select>
            </div>
            <div class="form-group">
              <label for="hook-description">{{ t('hooks.form.description') }}</label>
              <input id="hook-description" v-model="formData.description" type="text" :placeholder="t('hooks.form.briefDescriptionPlaceholder')" />
            </div>
            <div class="form-group">
              <label for="hook-content">{{ t('hooks.form.contentMarkdown') }}</label>
              <textarea id="hook-content" v-model="formData.content" rows="6" :placeholder="t('hooks.form.contentPlaceholder')"></textarea>
            </div>
            <div class="form-group checkbox-group">
              <label>
                <input type="checkbox" v-model="formData.enabled" />
                {{ t('hooks.form.enabled') }}
              </label>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn" @click="showCreateModal = false">{{ t('common.cancel') }}</button>
              <button type="submit" class="btn btn-primary" :disabled="isCreating">
                {{ isCreating ? t('hooks.creating') : t('hooks.createHook') }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
    <!-- AI Generate Modal -->
    <Teleport to="body">
      <div v-if="showGenerateModal" ref="generateModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-generate-hook" tabindex="-1" @click.self="showGenerateModal = false" @keydown.escape="showGenerateModal = false">
        <div class="modal generate-modal">
          <h2 id="modal-title-generate-hook">{{ t('hooks.generateModal.title') }}</h2>
          <p>{{ t('hooks.generateModal.description') }}</p>
          <div class="form-group">
            <label for="gen-description">{{ t('hooks.form.description') }}</label>
            <textarea
              id="gen-description"
              v-model="generateDescription"
              rows="4"
              :placeholder="t('hooks.generateModal.placeholder')"
              :disabled="isGenerating"
            ></textarea>
          </div>
          <AiStreamingLog
            v-if="isGenerating"
            :log="generateLog"
            :is-streaming="isGenerating"
            :phase="generatePhase || t('hooks.generateModal.generatingPhase')"
            :hint="t('hooks.generateModal.streamingHint')"
          />
          <div class="modal-actions">
            <button class="btn" @click="showGenerateModal = false" :disabled="isGenerating">{{ t('common.cancel') }}</button>
            <button class="btn btn-primary" @click="generateHook" :disabled="isGenerating || generateDescription.trim().length < 10">
              {{ isGenerating ? t('hooks.generating') : t('common.create') }}
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

@media (max-width: 480px) {
  .hooks-grid {
    grid-template-columns: 1fr;
  }
}
</style>
