<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { triggerApi } from '../services/api';
import type { Trigger } from '../services/api';
import { scopeFiltersApi } from '../services/api/scope-filters';
import type { ScopeFilter, ScopeFilterPattern } from '../services/api/scope-filters';

const showToast = useToast();
const { t } = useI18n();

type FilterMode = 'allowlist' | 'denylist';
type PatternType = 'repo' | 'branch' | 'author';

interface TestResult {
  input: string;
  type: PatternType;
  matched: boolean;
  matchedBy?: string;
  fires: boolean;
}

const filters = ref<ScopeFilter[]>([]);
const loading = ref(false);
const loadError = ref<string | null>(null);

const selectedFilterId = ref<string | null>(null);
const newPattern = ref<Partial<ScopeFilterPattern>>({ type: 'repo', pattern: '', description: '' });
const testInput = ref('');
const testType = ref<PatternType>('repo');
const testResults = ref<TestResult[]>([]);
const addPatternOpen = ref(false);

// Create filter dialog state
const showCreateDialog = ref(false);
const triggers = ref<Trigger[]>([]);
const createTriggerId = ref('');
const createMode = ref<FilterMode>('denylist');
const isCreating = ref(false);

const selectedFilter = computed(() => filters.value.find((f) => f.id === selectedFilterId.value));

async function loadFilters() {
  loading.value = true;
  loadError.value = null;
  try {
    const resp = await scopeFiltersApi.list();
    filters.value = resp.filters;
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : t('repoScopeFilters.errors.loadFilters');
  } finally {
    loading.value = false;
  }
}

async function loadFilterDetail(filterId: string) {
  try {
    const detail = await scopeFiltersApi.get(filterId);
    const idx = filters.value.findIndex((f) => f.id === filterId);
    if (idx !== -1) {
      filters.value[idx] = detail;
    }
  } catch {
    showToast(t('repoScopeFilters.toasts.loadDetailsFailed'), 'error');
  }
}

async function openCreateDialog() {
  showCreateDialog.value = true;
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers ?? [];
  } catch {
    showToast(t('repoScopeFilters.toasts.loadTriggersFailed'), 'error');
  }
}

async function createFilter() {
  if (!createTriggerId.value) {
    showToast(t('repoScopeFilters.toasts.selectTriggerFirst'), 'error');
    return;
  }
  isCreating.value = true;
  try {
    await scopeFiltersApi.upsert({
      trigger_id: createTriggerId.value,
      mode: createMode.value,
      enabled: true,
    });
    showToast(t('repoScopeFilters.toasts.filterCreated'), 'success');
    showCreateDialog.value = false;
    createTriggerId.value = '';
    createMode.value = 'denylist';
    await loadFilters();
    await Promise.all(filters.value.map((f) => loadFilterDetail(f.id)));
  } catch {
    showToast(t('repoScopeFilters.toasts.createFilterFailed'), 'error');
  } finally {
    isCreating.value = false;
  }
}

onMounted(async () => {
  await loadFilters();
  // Pre-load patterns for all filters
  await Promise.all(filters.value.map((f) => loadFilterDetail(f.id)));
});

function modeLabel(mode: FilterMode): string {
  return mode === 'allowlist' ? t('repoScopeFilters.modes.allowlist') : t('repoScopeFilters.modes.denylist');
}

function modeColor(mode: FilterMode): string {
  return mode === 'allowlist' ? 'var(--accent-green)' : 'var(--accent-amber)';
}

function typeIcon(type: PatternType): string {
  return type === 'repo' ? '🗂' : type === 'branch' ? '🌿' : '👤';
}

function typeLabel(type: PatternType): string {
  const labels: Record<PatternType, string> = {
    repo: t('repoScopeFilters.types.repo'),
    branch: t('repoScopeFilters.types.branch'),
    author: t('repoScopeFilters.types.author'),
  };
  return labels[type];
}

async function removePattern(filter: ScopeFilter, patternId: string) {
  try {
    await scopeFiltersApi.deletePattern(filter.id, patternId);
    await loadFilterDetail(filter.id);
    showToast(t('repoScopeFilters.toasts.patternRemoved'), 'info');
  } catch {
    showToast(t('repoScopeFilters.toasts.removePatternFailed'), 'error');
  }
}

async function addPattern(filter: ScopeFilter) {
  if (!newPattern.value.pattern?.trim()) {
    showToast(t('repoScopeFilters.toasts.patternEmpty'), 'error');
    return;
  }
  try {
    new RegExp(newPattern.value.pattern);
  } catch {
    showToast(t('repoScopeFilters.toasts.invalidRegex'), 'error');
    return;
  }
  try {
    await scopeFiltersApi.addPattern(filter.id, {
      type: newPattern.value.type as PatternType,
      pattern: newPattern.value.pattern,
      description: newPattern.value.description || '',
    });
    await loadFilterDetail(filter.id);
    newPattern.value = { type: 'repo', pattern: '', description: '' };
    addPatternOpen.value = false;
    showToast(t('repoScopeFilters.toasts.patternAdded'), 'success');
  } catch {
    showToast(t('repoScopeFilters.toasts.addPatternFailed'), 'error');
  }
}

async function toggleFilter(filter: ScopeFilter) {
  const newEnabled = !filter.enabled;
  try {
    await scopeFiltersApi.update(filter.id, { enabled: newEnabled });
    filter.enabled = newEnabled;
    showToast(
      newEnabled
        ? t('repoScopeFilters.toasts.filterEnabled')
        : t('repoScopeFilters.toasts.filterDisabled'),
      'info',
    );
  } catch {
    showToast(t('repoScopeFilters.toasts.updateFilterFailed'), 'error');
  }
}

async function toggleMode(filter: ScopeFilter) {
  const newMode: FilterMode = filter.mode === 'allowlist' ? 'denylist' : 'allowlist';
  try {
    await scopeFiltersApi.update(filter.id, { mode: newMode });
    filter.mode = newMode;
    showToast(t('repoScopeFilters.toasts.switchedTo', { mode: modeLabel(newMode) }), 'info');
  } catch {
    showToast(t('repoScopeFilters.toasts.updateModeFailed'), 'error');
  }
}

function runTest() {
  if (!selectedFilter.value || !testInput.value.trim()) {
    showToast(t('repoScopeFilters.toasts.enterTestValue'), 'info');
    return;
  }
  const filter = selectedFilter.value;
  const relevant = (filter.patterns || []).filter((p) => p.type === testType.value);
  let matched = false;
  let matchedBy: string | undefined;
  for (const p of relevant) {
    try {
      if (new RegExp(p.pattern).test(testInput.value)) {
        matched = true;
        matchedBy = p.pattern;
        break;
      }
    } catch {
      // skip invalid patterns
    }
  }
  const fires =
    filter.mode === 'allowlist' ? matched : !matched;
  const verdict =
    filter.mode === 'allowlist'
      ? matched
        ? t('repoScopeFilters.verdicts.firesAllowlist')
        : t('repoScopeFilters.verdicts.skipsNotAllowlist')
      : matched
      ? t('repoScopeFilters.verdicts.skipsDenylist')
      : t('repoScopeFilters.verdicts.firesNotDenylist');
  testResults.value = [
    {
      input: testInput.value,
      type: testType.value,
      matched,
      fires,
      matchedBy: matched ? t('repoScopeFilters.verdicts.matchedBy', { verdict, pattern: matchedBy }) : verdict,
    },
    ...testResults.value,
  ].slice(0, 10);
  testInput.value = '';
}

const patternCount = computed(() =>
  filters.value.reduce((sum, f) => sum + (f.patterns?.length ?? 0), 0)
);
</script>

<template>
  <div class="page-container">
    <PageHeader
      :title="t('repoScopeFilters.title')"
      :subtitle="t('repoScopeFilters.subtitle')"
    >
      <template #actions>
        <button class="btn-primary" @click="openCreateDialog">{{ t('repoScopeFilters.createFilter') }}</button>
      </template>
    </PageHeader>

    <!-- Summary -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">{{ t('repoScopeFilters.stats.botsWithFilters') }}</div>
        <div class="stat-value">{{ filters.length }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('repoScopeFilters.stats.totalPatterns') }}</div>
        <div class="stat-value">{{ patternCount }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('repoScopeFilters.stats.allowlists') }}</div>
        <div class="stat-value" style="color: var(--accent-green)">
          {{ filters.filter((f) => f.mode === 'allowlist').length }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('repoScopeFilters.stats.denylists') }}</div>
        <div class="stat-value" style="color: var(--accent-amber)">
          {{ filters.filter((f) => f.mode === 'denylist').length }}
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading-state">{{ t('repoScopeFilters.loading') }}</div>

    <div v-else-if="loadError" class="error-state">
      <p>{{ loadError }}</p>
      <button class="btn-ghost" @click="loadFilters">{{ t('common.retry') }}</button>
    </div>

    <!-- Create Filter Dialog -->
    <div v-if="showCreateDialog" class="create-dialog">
      <div class="create-dialog-header">{{ t('repoScopeFilters.createDialog.title') }}</div>
      <div class="create-dialog-body">
        <div class="create-field">
          <label class="create-label">{{ t('repoScopeFilters.createDialog.trigger') }}</label>
          <select v-model="createTriggerId" class="filter-select">
            <option value="">{{ t('repoScopeFilters.createDialog.selectTrigger') }}</option>
            <option v-for="trig in triggers" :key="trig.id" :value="trig.id">{{ trig.name }}</option>
          </select>
        </div>
        <div class="create-field">
          <label class="create-label">{{ t('repoScopeFilters.createDialog.filterMode') }}</label>
          <select v-model="createMode" class="filter-select">
            <option value="denylist">{{ t('repoScopeFilters.createDialog.denylistOption') }}</option>
            <option value="allowlist">{{ t('repoScopeFilters.createDialog.allowlistOption') }}</option>
          </select>
        </div>
        <div class="create-actions">
          <button class="btn-ghost" @click="showCreateDialog = false">{{ t('common.cancel') }}</button>
          <button class="btn-primary" :disabled="isCreating || !createTriggerId" @click="createFilter">
            {{ isCreating ? t('repoScopeFilters.creating') : t('repoScopeFilters.createFilterShort') }}
          </button>
        </div>
      </div>
    </div>

    <div v-else class="main-layout">
      <!-- Filter list -->
      <div class="filter-list">
        <div
          v-for="filter in filters"
          :key="filter.id"
          class="filter-card"
          :class="{ selected: selectedFilterId === filter.id, disabled: !filter.enabled }"
          @click="selectedFilterId = selectedFilterId === filter.id ? null : filter.id"
        >
          <div class="filter-header">
            <span class="bot-name">{{ filter.trigger_name ?? filter.trigger_id }}</span>
            <span class="mode-badge" :style="{ background: modeColor(filter.mode) + '22', color: modeColor(filter.mode) }">
              {{ modeLabel(filter.mode) }}
            </span>
            <span class="enabled-badge" :class="{ active: filter.enabled }">
              {{ filter.enabled ? t('repoScopeFilters.active') : t('repoScopeFilters.disabled') }}
            </span>
          </div>
          <div class="pattern-summary">
            <span v-for="(count, type) in { repo: (filter.patterns || []).filter((p) => p.type === 'repo').length, branch: (filter.patterns || []).filter((p) => p.type === 'branch').length, author: (filter.patterns || []).filter((p) => p.type === 'author').length }" :key="type">
              <span v-if="(count as number) > 0" class="type-chip">
                {{ typeIcon(type as PatternType) }} {{ count }} {{ type }}
              </span>
            </span>
          </div>
          <div class="filter-meta">{{ t('repoScopeFilters.lastModified', { date: new Date(filter.updated_at).toLocaleDateString() }) }}</div>
        </div>

        <div v-if="filters.length === 0" class="empty-state">
          <p>{{ t('repoScopeFilters.emptyFilters') }}</p>
          <button class="btn-primary" style="margin-top: 12px;" @click="openCreateDialog">{{ t('repoScopeFilters.createFilter') }}</button>
        </div>
      </div>

      <!-- Detail panel -->
      <div v-if="selectedFilter" class="detail-panel">
        <!-- Actions -->
        <div class="panel-actions-top">
          <button class="btn-ghost" @click="toggleMode(selectedFilter)">
            {{ t('repoScopeFilters.switchTo', { mode: selectedFilter.mode === 'allowlist' ? t('repoScopeFilters.modes.denylist') : t('repoScopeFilters.modes.allowlist') }) }}
          </button>
          <button :class="selectedFilter.enabled ? 'btn-ghost' : 'btn-primary'" @click="toggleFilter(selectedFilter)">
            {{ selectedFilter.enabled ? t('repoScopeFilters.disable') : t('repoScopeFilters.enable') }}
          </button>
        </div>

        <!-- Patterns -->
        <div class="patterns-section">
          <div class="section-header">
            <h3>{{ t('repoScopeFilters.patternsHeading', { mode: modeLabel(selectedFilter.mode) }) }}</h3>
            <button class="btn-add" @click="addPatternOpen = !addPatternOpen">{{ t('repoScopeFilters.addPattern') }}</button>
          </div>

          <!-- Add pattern form -->
          <div v-if="addPatternOpen" class="add-pattern-form">
            <select v-model="newPattern.type" class="filter-select">
              <option value="repo">{{ t('repoScopeFilters.types.repo') }}</option>
              <option value="branch">{{ t('repoScopeFilters.types.branch') }}</option>
              <option value="author">{{ t('repoScopeFilters.types.author') }}</option>
            </select>
            <input
              v-model="newPattern.pattern"
              class="text-input"
              :placeholder="t('repoScopeFilters.regexPlaceholder')"
              type="text"
            />
            <input
              v-model="newPattern.description"
              class="text-input"
              :placeholder="t('repoScopeFilters.descriptionPlaceholder')"
              type="text"
            />
            <div class="form-actions">
              <button class="btn-primary" @click="addPattern(selectedFilter)">{{ t('common.add') }}</button>
              <button class="btn-ghost" @click="addPatternOpen = false">{{ t('common.cancel') }}</button>
            </div>
          </div>

          <div class="pattern-list">
            <div
              v-for="p in selectedFilter.patterns"
              :key="p.id"
              class="pattern-row"
            >
              <span class="pattern-type">{{ typeIcon(p.type) }} {{ typeLabel(p.type) }}</span>
              <code class="pattern-regex">{{ p.pattern }}</code>
              <span v-if="p.description" class="pattern-desc">{{ p.description }}</span>
              <button class="remove-btn" :title="t('repoScopeFilters.removePattern')" @click="removePattern(selectedFilter, p.id)">✕</button>
            </div>
            <div v-if="!selectedFilter.patterns || selectedFilter.patterns.length === 0" class="empty-patterns">
              {{ t('repoScopeFilters.noPatterns') }}
            </div>
          </div>
        </div>

        <!-- Test sandbox -->
        <div class="test-section">
          <h3>{{ t('repoScopeFilters.testFilter') }}</h3>
          <p class="test-desc">{{ t('repoScopeFilters.testDesc') }}</p>
          <div class="test-controls">
            <select v-model="testType" class="filter-select">
              <option value="repo">{{ t('repoScopeFilters.types.repo') }}</option>
              <option value="branch">{{ t('repoScopeFilters.types.branch') }}</option>
              <option value="author">{{ t('repoScopeFilters.types.authorShort') }}</option>
            </select>
            <input
              v-model="testInput"
              class="text-input test-input"
              :placeholder="testType === 'repo' ? t('repoScopeFilters.testPlaceholder.repo') : testType === 'branch' ? t('repoScopeFilters.testPlaceholder.branch') : t('repoScopeFilters.testPlaceholder.author')"
              type="text"
              @keydown.enter="runTest"
            />
            <button class="btn-primary" @click="runTest">{{ t('repoScopeFilters.test') }}</button>
          </div>
          <div v-if="testResults.length > 0" class="test-results">
            <div v-for="(result, idx) in testResults.slice(0, 5)" :key="idx" class="test-result-row">
              <span class="test-value">{{ result.type }}: <code>{{ result.input }}</code></span>
              <span class="test-verdict" :style="{ color: result.fires ? 'var(--accent-green)' : 'var(--accent-amber)' }">
                {{ result.matchedBy }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="panel-placeholder">
        <p>{{ t('repoScopeFilters.panelPlaceholder') }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
}

.loading-state {
  text-align: center;
  padding: 48px;
  color: var(--text-secondary);
  font-size: 13px;
}

.error-state {
  text-align: center;
  padding: 48px 24px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.error-state p {
  margin: 0 0 12px;
  color: #ef4444;
  font-size: 13px;
}

.create-dialog {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.create-dialog-header {
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
  font-weight: 600;
}

.create-dialog-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.create-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.create-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.create-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.main-layout {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 20px;
  align-items: start;
}

.filter-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.filter-card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.filter-card:hover {
  border-color: var(--accent-blue);
}

.filter-card.selected {
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 2px rgba(66, 135, 245, 0.15);
}

.filter-card.disabled {
  opacity: 0.6;
}

.filter-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.bot-name {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
}

.mode-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 10px;
}

.enabled-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}

.enabled-badge.active {
  color: var(--accent-green);
}

.pattern-summary {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.type-chip {
  font-size: 12px;
  background: var(--surface-3);
  padding: 2px 8px;
  border-radius: 10px;
  color: var(--text-secondary);
}

.filter-meta {
  font-size: 11px;
  color: var(--text-secondary);
}

.empty-state {
  text-align: center;
  padding: 32px;
  color: var(--text-secondary);
  font-size: 13px;
  background: var(--surface-2);
  border: 1px dashed var(--border);
  border-radius: 8px;
}

.detail-panel {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.panel-actions-top {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}

.btn-add {
  background: transparent;
  border: 1px dashed var(--border);
  color: var(--accent-blue);
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 6px;
  cursor: pointer;
}

.add-pattern-form {
  background: var(--surface-3);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.filter-select {
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.text-input {
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-family: monospace;
}

.form-actions {
  display: flex;
  gap: 8px;
}

.pattern-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pattern-row {
  display: grid;
  grid-template-columns: 110px 1fr 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: var(--surface-3);
  border-radius: 6px;
  font-size: 12px;
}

.pattern-type {
  color: var(--text-secondary);
}

.pattern-regex {
  font-family: monospace;
  font-size: 12px;
}

.pattern-desc {
  color: var(--text-secondary);
  font-size: 11px;
  font-style: italic;
}

.remove-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--accent-red);
  font-size: 14px;
  padding: 2px 4px;
}

.empty-patterns {
  text-align: center;
  padding: 16px;
  color: var(--text-secondary);
  font-size: 13px;
}

.test-section {
  border-top: 1px solid var(--border);
  padding-top: 16px;
}

.test-section h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 4px;
}

.test-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.test-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.test-input {
  flex: 1;
}

.test-results {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.test-result-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  background: var(--surface-3);
  border-radius: 6px;
  font-size: 12px;
}

.test-value code {
  font-family: monospace;
}

.test-verdict {
  font-size: 12px;
  font-weight: 600;
}

.btn-primary {
  background: var(--accent-blue);
  color: #fff;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.panel-placeholder {
  background: var(--surface-2);
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 48px 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
