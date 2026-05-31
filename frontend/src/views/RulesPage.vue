<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import type { Rule, RuleType } from '../services/api';
import { ruleApi, ApiError } from '../services/api';
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

const router = useRouter();
const route = useRoute();

const highlightId = computed(() => (route.query.highlightId as string) || null);

const showToast = useToast();
const { t } = useI18n();

// AI Generate state
const showGenerateModal = ref(false);
const generateDescription = ref('');
const isGenerating = ref(false);
const { log: generateLog, phase: generatePhase, startStream } = useStreamingGeneration();

const rules = ref<Rule[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const showDeleteConfirm = ref(false);
const ruleToDelete = ref<Rule | null>(null);
const deletingId = ref<number | null>(null);
const togglingId = ref<number | null>(null);
const showCreateModal = ref(false);

const createModalRef = ref<HTMLElement | null>(null);
const generateModalRef = ref<HTMLElement | null>(null);
useFocusTrap(createModalRef, showCreateModal);
useFocusTrap(generateModalRef, showGenerateModal);

// Filter state
const filterType = ref<RuleType | ''>('');
const filterProject = ref<string>('');

// Create/edit form
const formData = ref({
  name: '',
  rule_type: 'validation' as RuleType,
  description: '',
  condition: '',
  action: '',
  enabled: true,
  project_id: '',
});

// SlideOver detail/edit state
const selectedRule = ref<Rule | null>(null);
const editForm = reactive({
  name: '',
  rule_type: 'validation' as RuleType,
  description: '',
  condition: '',
  action: '',
  enabled: true,
});
const isSaving = ref(false);

const isDirty = computed(() => {
  if (!selectedRule.value) return false;
  return (
    editForm.name !== selectedRule.value.name ||
    editForm.rule_type !== selectedRule.value.rule_type ||
    editForm.description !== (selectedRule.value.description || '') ||
    editForm.condition !== (selectedRule.value.condition || '') ||
    editForm.action !== (selectedRule.value.action || '') ||
    editForm.enabled !== !!selectedRule.value.enabled
  );
});

function editInDesign() {
  if (!selectedRule.value) return;
  const id = selectedRule.value.id;
  closeDetail();
  router.push({ name: 'rule-design', params: { ruleId: id } });
}

function openDetail(rule: Rule) {
  selectedRule.value = rule;
  editForm.name = rule.name;
  editForm.rule_type = rule.rule_type;
  editForm.description = rule.description || '';
  editForm.condition = rule.condition || '';
  editForm.action = rule.action || '';
  editForm.enabled = !!rule.enabled;
}

// Highlight support — must be after rules ref and openDetail declaration
function tryHighlight() {
  const id = highlightId.value;
  if (!id || rules.value.length === 0) return;
  const rule = rules.value.find(r => r.name === id);
  if (rule) {
    openDetail(rule);
    nextTick(() => {
      const el = document.getElementById(`entity-${rule.id}`) || document.querySelector(`[data-entity-name="${id}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('highlight-pulse');
        setTimeout(() => el.classList.remove('highlight-pulse'), 2000);
      }
    });
  }
}
watch(highlightId, tryHighlight);
watch(() => rules.value.length, tryHighlight);

function closeDetail() {
  selectedRule.value = null;
}

async function saveDetail() {
  if (!selectedRule.value) return;
  isSaving.value = true;
  try {
    await ruleApi.update(selectedRule.value.id, {
      name: editForm.name,
      rule_type: editForm.rule_type,
      description: editForm.description,
      condition: editForm.condition,
      action: editForm.action,
      enabled: editForm.enabled,
    });
    showToast(t('rules.toasts.updated'), 'success');
    closeDetail();
    await loadRules();
  } catch (err: unknown) {
    showToast(err instanceof Error ? err.message : t('rules.toasts.updateFailed'), 'error');
  } finally {
    isSaving.value = false;
  }
}

const RULE_TYPES: RuleType[] = [
  'pre_check',
  'post_check',
  'validation',
];

const RULE_TYPE_LABELS = computed<Record<RuleType, string>>(() => ({
  pre_check: t('rules.ruleTypes.preCheck'),
  post_check: t('rules.ruleTypes.postCheck'),
  validation: t('rules.ruleTypes.validation'),
}));

const filteredRules = computed(() => {
  return rules.value.filter(r => {
    if (filterType.value && r.rule_type !== filterType.value) return false;
    if (filterProject.value === 'global' && r.project_id) return false;
    if (filterProject.value && filterProject.value !== 'global' && r.project_id !== filterProject.value) return false;
    return true;
  });
});

const { searchQuery, sortField, sortOrder, filteredAndSorted, resultCount, totalCount } = useListFilter({
  items: filteredRules,
  searchFields: ['name', 'description'] as (keyof Rule)[],
  storageKey: 'rules-list-filter',
});

const pagination = usePagination({ defaultPageSize: 25, storageKey: 'rules-pagination' });

const listSortOptions = computed(() => [
  { value: 'name', label: t('rules.sort.name') },
  { value: 'created_at', label: t('rules.sort.dateCreated') },
]);

useWebMcpPageTools({
  page: 'RulesPage',
  domain: 'rules',
  stateGetter: () => ({
    items: rules.value,
    itemCount: rules.value.length,
    isLoading: isLoading.value,
    error: loadError.value,
    searchQuery: searchQuery.value,
    sortField: sortField.value,
    sortOrder: sortOrder.value,
    currentPage: pagination.currentPage.value,
    pageSize: pagination.pageSize.value,
    totalCount: pagination.totalCount.value,
    filterType: filterType.value,
  }),
  modalGetter: () => ({
    showCreateModal: showCreateModal.value,
    showDeleteConfirm: showDeleteConfirm.value,
    formValues: formData.value,
  }),
  modalActions: {
    openCreate: () => { showCreateModal.value = true; },
    openDelete: (id: string) => {
      const rule = rules.value.find((r) => String(r.id) === id);
      if (rule) { ruleToDelete.value = rule; showDeleteConfirm.value = true; }
    },
  },
  deps: [rules, searchQuery, sortField, sortOrder],
});

async function loadRules() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await ruleApi.list(undefined, { limit: pagination.pageSize.value, offset: pagination.offset.value });
    rules.value = data.rules || [];
    if (data.total_count != null) pagination.totalCount.value = data.total_count;
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : t('rules.toasts.loadFailed');
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => {
  loadRules();
});

watch([searchQuery, sortField, sortOrder], () => {
  pagination.resetToFirstPage();
});

watch([filterType, filterProject], () => {
  pagination.resetToFirstPage();
  loadRules();
});

function confirmDelete(rule: Rule) {
  ruleToDelete.value = rule;
  showDeleteConfirm.value = true;
}

async function deleteRule() {
  if (!ruleToDelete.value) return;
  deletingId.value = ruleToDelete.value.id;
  try {
    await ruleApi.delete(ruleToDelete.value.id);
    showToast(t('rules.toasts.deleted', { name: ruleToDelete.value.name }), 'success');
    showDeleteConfirm.value = false;
    ruleToDelete.value = null;
    await loadRules();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(t('rules.toasts.deleteFailed'), 'error');
    }
  } finally {
    deletingId.value = null;
  }
}

async function toggleEnabled(rule: Rule) {
  togglingId.value = rule.id;
  try {
    await ruleApi.update(rule.id, { enabled: !rule.enabled });
    await loadRules();
  } catch (e) {
    showToast(t('rules.toasts.updateFailed'), 'error');
  } finally {
    togglingId.value = null;
  }
}

function openCreateModal() {
  formData.value = {
    name: '',
    rule_type: 'validation',
    description: '',
    condition: '',
    action: '',
    enabled: true,
    project_id: '',
  };
  showCreateModal.value = true;
}

const isCreating = ref(false);
async function createRule() {
  if (isCreating.value) return;
  if (!formData.value.name.trim()) {
    showToast(t('rules.toasts.nameRequired'), 'error');
    return;
  }
  isCreating.value = true;
  try {
    await ruleApi.create({
      name: formData.value.name,
      rule_type: formData.value.rule_type,
      description: formData.value.description || undefined,
      condition: formData.value.condition || undefined,
      action: formData.value.action || undefined,
      enabled: formData.value.enabled,
      project_id: formData.value.project_id || undefined,
    });
    showToast(t('rules.toasts.created', { name: formData.value.name }), 'success');
    showCreateModal.value = false;
    await loadRules();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(t('rules.toasts.createFailed'), 'error');
    }
  } finally {
    isCreating.value = false;
  }
}

function getTypeColor(ruleType: RuleType): string {
  const colors: Record<RuleType, string> = {
    pre_check: '#00d4ff',
    post_check: '#00ff88',
    validation: '#8855ff',
  };
  return colors[ruleType] || '#a0a0b0';
}

async function generateRule() {
  if (!generateDescription.value.trim() || generateDescription.value.trim().length < 10) {
    showToast(t('rules.toasts.descriptionTooShort'), 'error');
    return;
  }
  isGenerating.value = true;
  try {
    const result = await startStream<{ config: Record<string, string>; warnings: string[] }>(
      '/admin/rules/generate/stream',
      { description: generateDescription.value.trim() },
    );
    if (result?.config) {
      formData.value.name = result.config.name || '';
      formData.value.rule_type = (result.config.rule_type || 'validation') as RuleType;
      formData.value.description = result.config.description || '';
      formData.value.condition = result.config.condition || '';
      formData.value.action = result.config.action || '';
      showGenerateModal.value = false;
      showCreateModal.value = true;
      showToast(t('rules.toasts.generated'), 'success');
    }
  } catch {
    showToast(t('rules.toasts.generateFailed'), 'error');
  } finally {
    isGenerating.value = false;
  }
}

onMounted(() => {
  loadRules();
});
</script>

<template>
  <PageLayout >
    <PageHeader :title="t('rules.title')" :subtitle="t('rules.subtitle')">
      <template #actions>
        <button class="btn btn-ai" @click="showGenerateModal = true">
          <span class="ai-badge">AI</span>
          {{ t('rules.generateRule') }}
        </button>
        <button class="btn btn-design" @click="router.push({ name: 'rule-design' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 11l3 3L22 4"/>
            <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
          </svg>
          {{ t('rules.designRule') }}
        </button>
        <button class="btn btn-primary" @click="openCreateModal">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          {{ t('rules.newRule') }}
        </button>
      </template>
    </PageHeader>

    <!-- Filters -->
    <div class="filters-bar">
      <div class="filter-group">
        <label>{{ t('rules.filters.ruleType') }}</label>
        <select v-model="filterType">
          <option value="">{{ t('rules.filters.allTypes') }}</option>
          <option v-for="ruleType in RULE_TYPES" :key="ruleType" :value="ruleType">{{ RULE_TYPE_LABELS[ruleType] }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label>{{ t('rules.filters.scope') }}</label>
        <select v-model="filterProject">
          <option value="">{{ t('rules.filters.all') }}</option>
          <option value="global">{{ t('rules.filters.globalOnly') }}</option>
        </select>
      </div>
    </div>

    <ListSearchSort
      v-if="!isLoading && !loadError && rules.length > 0"
      v-model:searchQuery="searchQuery"
      v-model:sortField="sortField"
      v-model:sortOrder="sortOrder"
      :sort-options="listSortOptions"
      :result-count="resultCount"
      :total-count="totalCount"
      :placeholder="t('rules.searchPlaceholder')"
    />

    <LoadingState v-if="isLoading" :message="t('rules.loading')" />

    <ErrorState
      v-else-if="loadError"
      :title="t('rules.errorTitle')"
      :message="loadError"
      @retry="loadRules"
    />

    <EmptyState
      v-else-if="rules.length === 0"
      :title="t('rules.empty.title')"
      :description="t('rules.empty.description')"
    >
      <template #actions>
        <button class="btn btn-primary" @click="openCreateModal">{{ t('rules.createRule') }}</button>
      </template>
    </EmptyState>

    <EmptyState
      v-else-if="filteredAndSorted.length === 0"
      :title="t('rules.noMatch.title')"
      :description="t('rules.noMatch.description')"
    />

    <div v-else class="rules-grid">
      <div
        v-for="rule in filteredAndSorted"
        :key="rule.id"
        :id="'entity-' + rule.id"
        :data-entity-name="rule.name"
        class="rule-card clickable"
        :class="{ disabled: !rule.enabled }"
        @click="openDetail(rule)"
      >
        <div class="rule-header">
          <div class="rule-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M9 11l3 3L22 4"/>
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
            </svg>
          </div>
          <div class="rule-info">
            <h3>{{ rule.name }}</h3>
            <span class="rule-type" :style="{ backgroundColor: getTypeColor(rule.rule_type) + '20', color: getTypeColor(rule.rule_type) }">
              {{ RULE_TYPE_LABELS[rule.rule_type] }}
            </span>
          </div>
          <div class="rule-status" :class="{ enabled: rule.enabled }">
            {{ rule.enabled ? t('rules.active') : t('rules.disabled') }}
          </div>
        </div>

        <p v-if="rule.description" class="rule-description">{{ rule.description }}</p>

        <div class="rule-meta">
          <div class="meta-item">
            <span class="meta-label">{{ t('rules.meta.scope') }}</span>
            <span class="meta-value">{{ rule.project_id ? t('rules.meta.project') : t('rules.meta.global') }}</span>
          </div>
          <div v-if="rule.source_path" class="meta-item">
            <span class="meta-label">{{ t('rules.meta.source') }}</span>
            <span class="meta-value source-path">{{ rule.source_path }}</span>
          </div>
        </div>

        <div v-if="rule.condition" class="rule-code" @click.stop>
          <div class="code-label">{{ t('rules.conditionLabel') }}</div>
          <pre class="code-block">{{ rule.condition }}</pre>
        </div>

        <div v-if="rule.action" class="rule-code" @click.stop>
          <div class="code-label">{{ t('rules.actionLabel') }}</div>
          <pre class="code-block">{{ rule.action }}</pre>
        </div>

        <div class="rule-actions">
          <button class="btn btn-small" @click.stop="toggleEnabled(rule)" :disabled="togglingId === rule.id">
            <span v-if="togglingId === rule.id" class="btn-spinner"></span>
            {{ togglingId === rule.id ? '...' : (rule.enabled ? t('rules.disable') : t('rules.enable')) }}
          </button>
          <button class="btn btn-small btn-danger" @click.stop="confirmDelete(rule)" :disabled="deletingId === rule.id">
            <span v-if="deletingId === rule.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <PaginationBar
      v-if="!isLoading && !loadError && rules.length > 0"
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
    <SlideOver :open="!!selectedRule" @close="closeDetail" :title="selectedRule?.name || t('rules.ruleDetails')" :dirty="isDirty">
      <div class="detail-form">
        <div class="form-group">
          <label>{{ t('rules.fields.name') }}</label>
          <input v-model="editForm.name" type="text" :placeholder="t('rules.placeholders.name')" />
        </div>
        <div class="form-group">
          <label>{{ t('rules.fields.ruleType') }}</label>
          <select v-model="editForm.rule_type">
            <option v-for="ruleType in RULE_TYPES" :key="ruleType" :value="ruleType">{{ RULE_TYPE_LABELS[ruleType] }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>{{ t('rules.fields.description') }}</label>
          <textarea v-model="editForm.description" rows="3" :placeholder="t('rules.placeholders.description')"></textarea>
        </div>
        <div class="form-group">
          <label>{{ t('rules.fields.condition') }}</label>
          <textarea v-model="editForm.condition" rows="4" :placeholder="t('rules.placeholders.conditionExpr')" class="code-textarea"></textarea>
        </div>
        <div class="form-group">
          <label>{{ t('rules.fields.action') }}</label>
          <textarea v-model="editForm.action" rows="4" :placeholder="t('rules.placeholders.actionExec')" class="code-textarea"></textarea>
        </div>
        <div class="form-group">
          <label class="toggle-label">
            <span>{{ t('rules.fields.enabled') }}</span>
            <div class="toggle-switch" :class="{ active: editForm.enabled }" @click="editForm.enabled = !editForm.enabled">
              <div class="toggle-knob"></div>
            </div>
          </label>
        </div>
      </div>
      <template #footer>
        <button class="btn btn-design-sm" @click="editInDesign">{{ t('rules.editInDesigner') }}</button>
        <button class="btn" @click="closeDetail">{{ t('common.cancel') }}</button>
        <button class="btn btn-primary" @click="saveDetail" :disabled="isSaving || !editForm.name.trim()">
          {{ isSaving ? t('rules.saving') : t('rules.saveChanges') }}
        </button>
      </template>
    </SlideOver>

    <ConfirmModal
      :open="showDeleteConfirm"
      :title="t('rules.deleteModal.title')"
      :message="t('rules.deleteModal.message', { name: ruleToDelete?.name })"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      variant="danger"
      @confirm="deleteRule"
      @cancel="showDeleteConfirm = false"
    />

    <!-- Create Rule Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal" ref="createModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-rule" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal create-modal">
          <h2 id="modal-title-create-rule">{{ t('rules.createModal.title') }}</h2>
          <form @submit.prevent="createRule">
            <div class="form-group">
              <label for="rule-name">{{ t('rules.fields.nameRequired') }}</label>
              <input id="rule-name" v-model="formData.name" type="text" placeholder="my-rule" required />
            </div>
            <div class="form-group">
              <label for="rule-type">{{ t('rules.fields.ruleTypeRequired') }}</label>
              <select id="rule-type" v-model="formData.rule_type" required>
                <option v-for="ruleType in RULE_TYPES" :key="ruleType" :value="ruleType">{{ RULE_TYPE_LABELS[ruleType] }}</option>
              </select>
            </div>
            <div class="form-group">
              <label for="rule-description">{{ t('rules.fields.description') }}</label>
              <input id="rule-description" v-model="formData.description" type="text" :placeholder="t('rules.placeholders.briefDescription')" />
            </div>
            <div class="form-group">
              <label for="rule-condition">{{ t('rules.fields.condition') }}</label>
              <textarea id="rule-condition" v-model="formData.condition" rows="4" :placeholder="t('rules.placeholders.conditionEval')"></textarea>
            </div>
            <div class="form-group">
              <label for="rule-action">{{ t('rules.fields.action') }}</label>
              <textarea id="rule-action" v-model="formData.action" rows="4" :placeholder="t('rules.placeholders.actionTaken')"></textarea>
            </div>
            <div class="form-group checkbox-group">
              <label>
                <input type="checkbox" v-model="formData.enabled" />
                {{ t('rules.fields.enabled') }}
              </label>
            </div>
            <div class="modal-actions">
              <button type="button" class="btn" @click="showCreateModal = false">{{ t('common.cancel') }}</button>
              <button type="submit" class="btn btn-primary" :disabled="isCreating">
                {{ isCreating ? t('rules.creating') : t('rules.createRule') }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
    <!-- AI Generate Modal -->
    <Teleport to="body">
      <div v-if="showGenerateModal" ref="generateModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-generate-rule" tabindex="-1" @click.self="showGenerateModal = false" @keydown.escape="showGenerateModal = false">
        <div class="modal generate-modal">
          <h2 id="modal-title-generate-rule">{{ t('rules.generateModal.title') }}</h2>
          <p>{{ t('rules.generateModal.description') }}</p>
          <div class="form-group">
            <label for="gen-description">{{ t('rules.fields.description') }}</label>
            <textarea
              id="gen-description"
              v-model="generateDescription"
              rows="4"
              :placeholder="t('rules.generateModal.placeholder')"
              :disabled="isGenerating"
            ></textarea>
          </div>
          <AiStreamingLog
            v-if="isGenerating"
            :log="generateLog"
            :is-streaming="isGenerating"
            :phase="generatePhase || t('rules.generateModal.phase')"
            :hint="t('rules.generateModal.hint')"
          />
          <div class="modal-actions">
            <button class="btn" @click="showGenerateModal = false" :disabled="isGenerating">{{ t('common.cancel') }}</button>
            <button class="btn btn-primary" @click="generateRule" :disabled="isGenerating || generateDescription.trim().length < 10">
              {{ isGenerating ? t('rules.generating') : t('rules.generate') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </PageLayout>
</template>

<style scoped>
.rules-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 20px;
}

.rule-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
  transition: border-color 0.2s;
}

.rule-card:hover {
  border-color: var(--border-strong);
}

.rule-card.clickable {
  cursor: pointer;
}

.rule-card.clickable:hover {
  border-color: var(--accent-primary, #6366f1);
}

.rule-card.disabled {
  opacity: 0.6;
}

.rule-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.rule-icon {
  width: 44px;
  height: 44px;
  background: var(--accent-violet-dim);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.rule-icon svg {
  width: 24px;
  height: 24px;
  color: var(--accent-violet);
}

.rule-info {
  flex: 1;
  min-width: 0;
}

.rule-info h3 {
  margin: 0 0 6px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rule-type {
  display: inline-block;
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
}

.rule-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.rule-status.enabled {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.rule-description {
  color: var(--text-secondary);
  font-size: 14px;
  margin: 0 0 16px 0;
  line-height: 1.5;
}

.rule-meta {
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

.rule-code {
  margin-bottom: 16px;
}

.code-label {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}

.code-block {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 8px 12px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  overflow-x: auto;
  margin: 0;
  max-height: 100px;
  overflow-y: auto;
}

.rule-actions {
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
  .rules-grid {
    grid-template-columns: 1fr;
  }
}
</style>
