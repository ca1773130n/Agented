<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter, useRoute } from 'vue-router';
import type { Command } from '../services/api';
import { commandApi, ApiError } from '../services/api';
import AiStreamingLog from '../components/ai/AiStreamingLog.vue';
import { useStreamingGeneration } from '../composables/useStreamingGeneration';
import PageLayout from '../components/base/PageLayout.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import LoadingState from '../components/base/LoadingState.vue';
import ListSearchSort from '../components/base/ListSearchSort.vue';
import PaginationBar from '../components/base/PaginationBar.vue';
import SlideOver from '../components/base/SlideOver.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useListFilter } from '../composables/useListFilter';
import { usePagination } from '../composables/usePagination';
import { useWebMcpPageTools } from '../composables/useWebMcpPageTools';

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

const commands = ref<Command[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const showDeleteConfirm = ref(false);
const commandToDelete = ref<Command | null>(null);
const deletingId = ref<number | null>(null);
const togglingId = ref<number | null>(null);
const showCreateModal = ref(false);

const createModalRef = ref<HTMLElement | null>(null);
const generateModalRef = ref<HTMLElement | null>(null);
useFocusTrap(createModalRef, showCreateModal);
useFocusTrap(generateModalRef, showGenerateModal);

// Filter state
const filterProject = ref<string>('');

// Create/edit form
const formData = ref({
  name: '',
  description: '',
  content: '',
  arguments: '',
  enabled: true,
  project_id: '',
});

// SlideOver detail/edit state
const selectedCommand = ref<Command | null>(null);
const editForm = reactive({
  name: '',
  description: '',
  content: '',
  arguments: '',
  enabled: true,
});
const isSaving = ref(false);

const isDirty = computed(() => {
  if (!selectedCommand.value) return false;
  return (
    editForm.name !== selectedCommand.value.name ||
    editForm.description !== (selectedCommand.value.description || '') ||
    editForm.content !== (selectedCommand.value.content || '') ||
    editForm.arguments !== (selectedCommand.value.arguments || '') ||
    editForm.enabled !== !!selectedCommand.value.enabled
  );
});

function editInDesign() {
  if (!selectedCommand.value) return;
  const id = selectedCommand.value.id;
  closeDetail();
  router.push({ name: 'command-design', params: { commandId: id } });
}

function openDetail(command: Command) {
  selectedCommand.value = command;
  editForm.name = command.name;
  editForm.description = command.description || '';
  editForm.content = command.content || '';
  editForm.arguments = command.arguments || '';
  editForm.enabled = !!command.enabled;
}

function closeDetail() {
  selectedCommand.value = null;
}

function tryHighlight() {
  const id = highlightId.value;
  if (!id || commands.value.length === 0) return;
  const cmd = commands.value.find(c => c.name === id);
  if (cmd) {
    openDetail(cmd);
    nextTick(() => {
      const el = document.getElementById(`entity-${cmd.id}`) || document.querySelector(`[data-entity-name="${id}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('highlight-pulse');
        setTimeout(() => el.classList.remove('highlight-pulse'), 2000);
      }
    });
  }
}
watch(highlightId, tryHighlight);
watch(() => commands.value.length, tryHighlight);

async function saveDetail() {
  if (!selectedCommand.value) return;
  if (editForm.arguments && editForm.arguments.trim()) {
    const validation = validateArguments(editForm.arguments);
    if (!validation.valid) {
      showToast(validation.error || t('commands.toast.invalidJson'), 'error');
      return;
    }
  }
  isSaving.value = true;
  try {
    await commandApi.update(selectedCommand.value.id, {
      name: editForm.name,
      description: editForm.description,
      content: editForm.content,
      arguments: editForm.arguments,
      enabled: editForm.enabled,
    });
    showToast(t('commands.toast.updated'), 'success');
    closeDetail();
    await loadCommands();
  } catch (err: unknown) {
    showToast(err instanceof Error ? err.message : t('commands.toast.updateFailed'), 'error');
  } finally {
    isSaving.value = false;
  }
}

// Client-side scope filter (project) the server list does not handle.
// Search + sort are now server-driven (see loadCommands); this only narrows the
// already-fetched, server-filtered page.
const displayCommands = computed(() => {
  return commands.value.filter(c => {
    if (filterProject.value === 'global' && c.project_id) return false;
    if (filterProject.value && filterProject.value !== 'global' && c.project_id !== filterProject.value) return false;
    return true;
  });
});

// useListFilter still owns the search/sort UI state + sessionStorage persistence;
// we drive the SERVER call with these refs instead of its client-side filteredAndSorted.
const { searchQuery, sortField, sortOrder } = useListFilter({
  items: commands,
  searchFields: ['name', 'description'] as (keyof Command)[],
  storageKey: 'commands-list-filter',
});

const pagination = usePagination({ defaultPageSize: 25, storageKey: 'commands-pagination' });

const listSortOptions = [
  { value: 'name', label: t('commands.sort.name') },
  { value: 'created_at', label: t('commands.sort.dateCreated') },
];

useWebMcpPageTools({
  page: 'CommandsPage',
  domain: 'commands',
  stateGetter: () => ({
    items: commands.value,
    itemCount: commands.value.length,
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
    formValues: formData.value,
  }),
  modalActions: {
    openCreate: () => { showCreateModal.value = true; },
    openDelete: (id: string) => {
      const command = commands.value.find((c) => String(c.id) === id);
      if (command) { commandToDelete.value = command; showDeleteConfirm.value = true; }
    },
  },
  deps: [commands, searchQuery, sortField, sortOrder],
});

async function loadCommands() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await commandApi.list(undefined, {
      limit: pagination.pageSize.value,
      offset: pagination.offset.value,
      search: searchQuery.value.trim() || undefined,
      sort: sortField.value as 'name' | 'created_at' | 'updated_at',
      order: sortOrder.value,
    });
    commands.value = data.commands || [];
    if (data.total_count != null) pagination.totalCount.value = data.total_count;
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : t('commands.toast.loadFailed');
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => { loadCommands(); });
// Debounce search so we don't fire a request per keystroke (~300ms).
let searchDebounce: ReturnType<typeof setTimeout> | undefined;
watch(searchQuery, () => {
  if (searchDebounce) clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    pagination.resetToFirstPage();
    loadCommands();
  }, 300);
});
// Sort changes refetch immediately (reset to page 1).
watch([sortField, sortOrder], () => { pagination.resetToFirstPage(); loadCommands(); });
watch(filterProject, () => { pagination.resetToFirstPage(); loadCommands(); });

function confirmDelete(command: Command) {
  commandToDelete.value = command;
  showDeleteConfirm.value = true;
}

async function deleteCommand() {
  if (!commandToDelete.value) return;
  deletingId.value = commandToDelete.value.id;
  try {
    await commandApi.delete(commandToDelete.value.id);
    showToast(t('commands.toast.deleted', { name: commandToDelete.value.name }), 'success');
    showDeleteConfirm.value = false;
    commandToDelete.value = null;
    await loadCommands();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(t('commands.toast.deleteFailed'), 'error');
    }
  } finally {
    deletingId.value = null;
  }
}

async function toggleEnabled(command: Command) {
  togglingId.value = command.id;
  try {
    await commandApi.update(command.id, { enabled: !command.enabled });
    await loadCommands();
  } catch (e) {
    showToast(t('commands.toast.updateFailed'), 'error');
  } finally {
    togglingId.value = null;
  }
}

function openCreateModal() {
  formData.value = {
    name: '',
    description: '',
    content: '',
    arguments: '',
    enabled: true,
    project_id: '',
  };
  showCreateModal.value = true;
}

// Tracks the in-flight create so the modal's submit button is
// disabled while the request is on the wire (prevents double-submit
// duplicates). Mirrors the existing ``isSaving`` ref used by saveDetail.
const isCreating = ref(false);
async function createCommand() {
  if (isCreating.value) return;
  if (!formData.value.name.trim()) {
    showToast(t('commands.toast.nameRequired'), 'error');
    return;
  }
  if (formData.value.arguments && formData.value.arguments.trim()) {
    const validation = validateArguments(formData.value.arguments);
    if (!validation.valid) {
      showToast(validation.error || t('commands.toast.invalidJson'), 'error');
      return;
    }
  }
  isCreating.value = true;
  try {
    await commandApi.create({
      name: formData.value.name,
      description: formData.value.description || undefined,
      content: formData.value.content || undefined,
      arguments: formData.value.arguments || undefined,
      enabled: formData.value.enabled,
      project_id: formData.value.project_id || undefined,
    });
    showToast(t('commands.toast.created', { name: formData.value.name }), 'success');
    showCreateModal.value = false;
    await loadCommands();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(t('commands.toast.createFailed'), 'error');
    }
  } finally {
    isCreating.value = false;
  }
}

function parseArguments(argsStr: string | undefined): string[] {
  if (!argsStr) return [];
  try {
    const parsed = JSON.parse(argsStr);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function validateArguments(argsStr: string | undefined): { valid: boolean; error?: string; args: string[] } {
  if (!argsStr || !argsStr.trim()) return { valid: true, args: [] };
  try {
    const parsed = JSON.parse(argsStr);
    if (!Array.isArray(parsed)) return { valid: false, error: t('commands.toast.argsMustBeArray'), args: [] };
    return { valid: true, args: parsed };
  } catch (e) {
    return { valid: false, error: t('commands.toast.invalidJsonDetail', { detail: e instanceof Error ? e.message : 'parse error' }), args: [] };
  }
}

async function generateCommand() {
  if (!generateDescription.value.trim() || generateDescription.value.trim().length < 10) {
    showToast(t('commands.toast.descriptionTooShort'), 'error');
    return;
  }
  isGenerating.value = true;
  try {
    const result = await startStream<{ config: Record<string, string>; warnings: string[] }>(
      '/admin/commands/generate/stream',
      { description: generateDescription.value.trim() },
    );
    if (result?.config) {
      formData.value.name = result.config.name || '';
      formData.value.description = result.config.description || '';
      formData.value.content = result.config.content || '';
      formData.value.arguments = typeof result.config.arguments === 'string'
        ? result.config.arguments
        : JSON.stringify(result.config.arguments || []);
      showGenerateModal.value = false;
      showCreateModal.value = true;
      showToast(t('commands.toast.configGenerated'), 'success');
    }
  } catch {
    showToast(t('commands.toast.generateFailed'), 'error');
  } finally {
    isGenerating.value = false;
  }
}

onMounted(() => {
  loadCommands();
});
</script>

<template>
  <PageLayout >
    <PageHeader :title="t('commands.title')" :subtitle="t('commands.subtitle')">
      <template #actions>
        <button class="btn btn-ai" @click="showGenerateModal = true">
          <span class="ai-badge">AI</span>
          {{ t('commands.generateCommand') }}
        </button>
        <button class="btn btn-design" @click="router.push({ name: 'command-design' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="4 17 10 11 4 5"/>
            <line x1="12" y1="19" x2="20" y2="19"/>
          </svg>
          {{ t('commands.designCommand') }}
        </button>
        <button class="btn btn-primary" @click="openCreateModal">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          {{ t('commands.newCommand') }}
        </button>
      </template>
    </PageHeader>

    <!-- Filters -->
    <div class="filters-bar">
      <div class="filter-group">
        <label>{{ t('commands.scope') }}</label>
        <select v-model="filterProject">
          <option value="">{{ t('commands.scopeAll') }}</option>
          <option value="global">{{ t('commands.scopeGlobalOnly') }}</option>
        </select>
      </div>
    </div>

    <ListSearchSort
      v-if="!isLoading && !loadError && commands.length > 0"
      v-model:searchQuery="searchQuery"
      v-model:sortField="sortField"
      v-model:sortOrder="sortOrder"
      :sort-options="listSortOptions"
      :result-count="displayCommands.length"
      :total-count="pagination.totalCount.value"
      :placeholder="t('commands.searchPlaceholder')"
    />

    <LoadingState v-if="isLoading" :message="t('commands.loading')" />

    <ErrorState
      v-else-if="loadError"
      :title="t('commands.loadErrorTitle')"
      :message="loadError"
      @retry="loadCommands"
    />

    <EmptyState
      v-else-if="commands.length === 0"
      :title="t('commands.emptyTitle')"
      :description="t('commands.emptyDescription')"
    >
      <template #actions>
        <button class="btn btn-primary" @click="openCreateModal">{{ t('commands.createCommand') }}</button>
      </template>
    </EmptyState>

    <EmptyState
      v-else-if="displayCommands.length === 0"
      :title="t('commands.noMatchTitle')"
      :description="t('commands.noMatchDescription')"
    />

    <div v-else class="commands-grid">
      <div
        v-for="command in displayCommands"
        :key="command.id"
        :id="'entity-' + command.id"
        :data-entity-name="command.name"
        class="command-card clickable"
        :class="{ disabled: !command.enabled }"
        @click="openDetail(command)"
      >
        <div class="command-header">
          <div class="command-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <polyline points="4 17 10 11 4 5"/>
              <line x1="12" y1="19" x2="20" y2="19"/>
            </svg>
          </div>
          <div class="command-info">
            <h3>/{{ command.name }}</h3>
          </div>
          <div class="command-status" :class="{ enabled: command.enabled }">
            {{ command.enabled ? t('commands.active') : t('commands.disabled') }}
          </div>
        </div>

        <p v-if="command.description" class="command-description">{{ command.description }}</p>

        <div class="command-meta">
          <div class="meta-item">
            <span class="meta-label">{{ t('commands.meta.scope') }}</span>
            <span class="meta-value">{{ command.project_id ? t('commands.meta.project') : t('commands.meta.global') }}</span>
          </div>
          <div v-if="command.arguments && command.arguments.trim()" class="meta-item">
            <span class="meta-label">{{ t('commands.meta.args') }}</span>
            <template v-if="validateArguments(command.arguments).valid">
              <span class="meta-value args-list">{{ parseArguments(command.arguments).join(', ') }}</span>
            </template>
            <span v-else class="meta-value args-error">{{ t('commands.invalidJson') }}</span>
          </div>
          <div v-if="command.source_path" class="meta-item">
            <span class="meta-label">{{ t('commands.meta.source') }}</span>
            <span class="meta-value source-path">{{ command.source_path }}</span>
          </div>
        </div>

        <div class="command-actions">
          <button class="btn btn-small" @click.stop="toggleEnabled(command)" :disabled="togglingId === command.id">
            <span v-if="togglingId === command.id" class="btn-spinner"></span>
            {{ togglingId === command.id ? '...' : (command.enabled ? t('commands.disable') : t('commands.enable')) }}
          </button>
          <button class="btn btn-small btn-danger" :aria-label="t('common.delete')" @click.stop="confirmDelete(command)" :disabled="deletingId === command.id">
            <span v-if="deletingId === command.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <PaginationBar
      v-if="!isLoading && !loadError && commands.length > 0"
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
    <SlideOver :open="!!selectedCommand" @close="closeDetail" :title="selectedCommand ? '/' + selectedCommand.name : t('commands.detailTitle')" :dirty="isDirty">
      <div class="detail-form">
        <div class="form-group">
          <label>{{ t('commands.field.nameWithoutSlash') }}</label>
          <input v-model="editForm.name" type="text" :placeholder="t('commands.field.namePlaceholder')" />
        </div>
        <div class="form-group">
          <label>{{ t('commands.field.description') }}</label>
          <textarea v-model="editForm.description" rows="3" :placeholder="t('commands.field.descriptionPlaceholder')"></textarea>
        </div>
        <div class="form-group">
          <label>{{ t('commands.field.content') }}</label>
          <textarea v-model="editForm.content" rows="8" :placeholder="t('commands.field.contentPlaceholder')" class="code-textarea"></textarea>
        </div>
        <div class="form-group">
          <label>{{ t('commands.field.arguments') }}</label>
          <textarea v-model="editForm.arguments" rows="4" :placeholder="t('commands.field.argumentsPlaceholder')" class="code-textarea"></textarea>
        </div>
        <div class="form-group">
          <label class="toggle-label">
            <span>{{ t('commands.enabled') }}</span>
            <div
              class="toggle-switch"
              :class="{ active: editForm.enabled }"
              role="switch"
              :aria-checked="editForm.enabled"
              :aria-label="t('commands.enabled')"
              tabindex="0"
              @click="editForm.enabled = !editForm.enabled"
              @keydown.enter.prevent="editForm.enabled = !editForm.enabled"
              @keydown.space.prevent="editForm.enabled = !editForm.enabled"
            >
              <div class="toggle-knob"></div>
            </div>
          </label>
        </div>
      </div>
      <template #footer>
        <button class="btn btn-design-sm" @click="editInDesign">{{ t('commands.editInDesigner') }}</button>
        <button class="btn" @click="closeDetail">{{ t('common.cancel') }}</button>
        <button class="btn btn-primary" @click="saveDetail" :disabled="isSaving || !editForm.name.trim()">
          {{ isSaving ? t('commands.saving') : t('commands.saveChanges') }}
        </button>
      </template>
    </SlideOver>

    <ConfirmModal
      :open="showDeleteConfirm"
      :title="t('commands.deleteTitle')"
      :message="t('commands.deleteMessage', { name: commandToDelete?.name })"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      variant="danger"
      @confirm="deleteCommand"
      @cancel="showDeleteConfirm = false"
    />

    <!-- Create Command Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal" ref="createModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-command" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal create-modal">
          <h2 id="modal-title-create-command">{{ t('commands.createModalTitle') }}</h2>
          <form @submit.prevent="createCommand">
            <div class="form-group">
              <label for="command-name">{{ t('commands.field.nameRequiredWithoutSlash') }}</label>
              <input id="command-name" v-model="formData.name" type="text" placeholder="my-command" required />
            </div>
            <div class="form-group">
              <label for="command-description">{{ t('commands.field.description') }}</label>
              <input id="command-description" v-model="formData.description" type="text" :placeholder="t('commands.field.briefDescriptionPlaceholder')" />
            </div>
            <div class="form-group">
              <label for="command-content">{{ t('commands.field.contentMarkdown') }}</label>
              <textarea id="command-content" v-model="formData.content" rows="6" :placeholder="t('commands.field.contentPlaceholder')"></textarea>
            </div>
            <div class="form-group">
              <label for="command-arguments">{{ t('commands.field.argumentsJsonArray') }}</label>
              <textarea
                id="command-arguments"
                v-model="formData.arguments"
                rows="4"
                placeholder='[
  { "name": "arg1", "type": "string", "required": true },
  { "name": "arg2", "type": "string", "required": false }
]'
                class="code-textarea"
              ></textarea>
            </div>
            <div class="form-group checkbox-group">
              <label>
                <input type="checkbox" v-model="formData.enabled" />
                {{ t('commands.enabled') }}
              </label>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn" @click="showCreateModal = false">{{ t('common.cancel') }}</button>
              <button type="submit" class="btn btn-primary" :disabled="isCreating">
                {{ isCreating ? t('commands.creating') : t('commands.createCommand') }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
    <!-- AI Generate Modal -->
    <Teleport to="body">
      <div v-if="showGenerateModal" ref="generateModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-generate-command" tabindex="-1" @click.self="showGenerateModal = false" @keydown.escape="showGenerateModal = false">
        <div class="modal generate-modal">
          <h2 id="modal-title-generate-command">{{ t('commands.generateModalTitle') }}</h2>
          <p>{{ t('commands.generateModalBody') }}</p>
          <div class="form-group">
            <label for="gen-description">{{ t('commands.field.description') }}</label>
            <textarea
              id="gen-description"
              v-model="generateDescription"
              rows="4"
              :placeholder="t('commands.generatePlaceholder')"
              :disabled="isGenerating"
            ></textarea>
          </div>
          <AiStreamingLog
            v-if="isGenerating"
            :log="generateLog"
            :is-streaming="isGenerating"
            :phase="generatePhase || t('commands.generatingConfig')"
            :hint="t('commands.streamingHint')"
          />
          <div class="modal-actions">
            <button class="btn" @click="showGenerateModal = false" :disabled="isGenerating">{{ t('common.cancel') }}</button>
            <button class="btn btn-primary" @click="generateCommand" :disabled="isGenerating || generateDescription.trim().length < 10">
              {{ isGenerating ? t('commands.generating') : t('commands.generate') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </PageLayout>
</template>

<style scoped>
.commands-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}

.command-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
  transition: border-color 0.2s;
}

.command-card:hover {
  border-color: var(--border-strong);
}

.command-card.clickable {
  cursor: pointer;
}

.command-card.clickable:hover {
  border-color: var(--accent-primary, #6366f1);
}

.command-card.disabled {
  opacity: 0.6;
}

.command-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.command-icon {
  width: 44px;
  height: 44px;
  background: var(--accent-amber-dim);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.command-icon svg {
  width: 24px;
  height: 24px;
  color: var(--accent-amber);
}

.command-info {
  flex: 1;
  min-width: 0;
}

.command-info h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--accent-cyan);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.command-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.command-status.enabled {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.command-description {
  color: var(--text-secondary);
  font-size: 14px;
  margin: 0 0 16px 0;
  line-height: 1.5;
}

.command-meta {
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

.meta-value.args-list {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent-violet);
}

.meta-value.args-error {
  color: var(--accent-crimson, #ff3366);
  font-size: 12px;
  font-style: italic;
}

.meta-value.source-path {
  font-family: var(--font-mono);
  font-size: 11px;
  max-width: 200px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.command-actions {
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
  .commands-grid {
    grid-template-columns: 1fr;
  }
}
</style>
