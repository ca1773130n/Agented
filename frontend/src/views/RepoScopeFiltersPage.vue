<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { scopeFiltersApi } from '../services/api/scope-filters';
import type { ScopeFilter, ScopeFilterPattern } from '../services/api/scope-filters';

const showToast = useToast();

type FilterMode = 'allowlist' | 'denylist';
type PatternType = 'repo' | 'branch' | 'author';

interface TestResult {
  input: string;
  type: PatternType;
  matched: boolean;
  matchedBy?: string;
}

const filters = ref<ScopeFilter[]>([]);
const loading = ref(false);

const selectedFilterId = ref<string | null>(null);
const newPattern = ref<Partial<ScopeFilterPattern>>({ type: 'repo', pattern: '', description: '' });
const testInput = ref('');
const testType = ref<PatternType>('repo');
const testResults = ref<TestResult[]>([]);
const addPatternOpen = ref(false);

const selectedFilter = computed(() => filters.value.find((f) => f.id === selectedFilterId.value));

async function loadFilters() {
  loading.value = true;
  try {
    const resp = await scopeFiltersApi.list();
    filters.value = resp.filters;
  } catch {
    showToast('Failed to load scope filters', 'error');
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
    showToast('Failed to load filter details', 'error');
  }
}

onMounted(async () => {
  await loadFilters();
  // Pre-load patterns for all filters
  await Promise.all(filters.value.map((f) => loadFilterDetail(f.id)));
});

function modeLabel(mode: FilterMode): string {
  return mode === 'allowlist' ? 'Allowlist' : 'Denylist';
}

function modeColor(mode: FilterMode): string {
  return mode === 'allowlist' ? 'var(--accent-green)' : 'var(--accent-amber)';
}

function typeIcon(type: PatternType): string {
  return type === 'repo' ? '🗂' : type === 'branch' ? '🌿' : '👤';
}

function typeLabel(type: PatternType): string {
  const labels: Record<PatternType, string> = { repo: 'Repository', branch: 'Branch', author: 'PR Author' };
  return labels[type];
}

async function removePattern(filter: ScopeFilter, patternId: string) {
  try {
    await scopeFiltersApi.deletePattern(filter.id, patternId);
    await loadFilterDetail(filter.id);
    showToast('Pattern removed', 'info');
  } catch {
    showToast('Failed to remove pattern', 'error');
  }
}

async function addPattern(filter: ScopeFilter) {
  if (!newPattern.value.pattern?.trim()) {
    showToast('Pattern cannot be empty', 'error');
    return;
  }
  try {
    new RegExp(newPattern.value.pattern);
  } catch {
    showToast('Invalid regex pattern', 'error');
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
    showToast('Pattern added', 'success');
  } catch {
    showToast('Failed to add pattern', 'error');
  }
}

async function toggleFilter(filter: ScopeFilter) {
  const newEnabled = !filter.enabled;
  try {
    await scopeFiltersApi.update(filter.id, { enabled: newEnabled });
    filter.enabled = newEnabled;
    showToast(`Scope filter ${newEnabled ? 'enabled' : 'disabled'}`, 'info');
  } catch {
    showToast('Failed to update filter', 'error');
  }
}

async function toggleMode(filter: ScopeFilter) {
  const newMode: FilterMode = filter.mode === 'allowlist' ? 'denylist' : 'allowlist';
  try {
    await scopeFiltersApi.update(filter.id, { mode: newMode });
    filter.mode = newMode;
    showToast(`Switched to ${modeLabel(newMode)}`, 'info');
  } catch {
    showToast('Failed to update filter mode', 'error');
  }
}

function runTest() {
  if (!selectedFilter.value || !testInput.value.trim()) {
    showToast('Enter a test value first', 'info');
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
    filter.mode === 'allowlist'
      ? matched
        ? 'Bot FIRES (allowlist match)'
        : 'Bot SKIPS (not in allowlist)'
      : matched
      ? 'Bot SKIPS (denylist match)'
      : 'Bot FIRES (not in denylist)';
  testResults.value = [
    {
      input: testInput.value,
      type: testType.value,
      matched,
      matchedBy: matched ? `${fires} — matched by: ${matchedBy}` : fires,
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
      title="Repository Scope Filters"
      subtitle="Define per-bot inclusion/exclusion patterns for repos, branches, and PR authors"
    />

    <!-- Summary -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">Bots with Filters</div>
        <div class="stat-value">{{ filters.length }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total Patterns</div>
        <div class="stat-value">{{ patternCount }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Allowlists</div>
        <div class="stat-value" style="color: var(--accent-green)">
          {{ filters.filter((f) => f.mode === 'allowlist').length }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Denylists</div>
        <div class="stat-value" style="color: var(--accent-amber)">
          {{ filters.filter((f) => f.mode === 'denylist').length }}
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading-state">Loading scope filters…</div>

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
              {{ filter.enabled ? 'Active' : 'Disabled' }}
            </span>
          </div>
          <div class="pattern-summary">
            <span v-for="(count, type) in { repo: (filter.patterns || []).filter((p) => p.type === 'repo').length, branch: (filter.patterns || []).filter((p) => p.type === 'branch').length, author: (filter.patterns || []).filter((p) => p.type === 'author').length }" :key="type">
              <span v-if="(count as number) > 0" class="type-chip">
                {{ typeIcon(type as PatternType) }} {{ count }} {{ type }}
              </span>
            </span>
          </div>
          <div class="filter-meta">Last modified {{ new Date(filter.updated_at).toLocaleDateString() }}</div>
        </div>

        <div v-if="filters.length === 0" class="empty-state">
          No scope filters configured yet.
        </div>
      </div>

      <!-- Detail panel -->
      <div v-if="selectedFilter" class="detail-panel">
        <!-- Actions -->
        <div class="panel-actions-top">
          <button class="btn-ghost" @click="toggleMode(selectedFilter)">
            Switch to {{ selectedFilter.mode === 'allowlist' ? 'Denylist' : 'Allowlist' }}
          </button>
          <button :class="selectedFilter.enabled ? 'btn-ghost' : 'btn-primary'" @click="toggleFilter(selectedFilter)">
            {{ selectedFilter.enabled ? 'Disable' : 'Enable' }}
          </button>
        </div>

        <!-- Patterns -->
        <div class="patterns-section">
          <div class="section-header">
            <h3>{{ modeLabel(selectedFilter.mode) }} Patterns</h3>
            <button class="btn-add" @click="addPatternOpen = !addPatternOpen">+ Add Pattern</button>
          </div>

          <!-- Add pattern form -->
          <div v-if="addPatternOpen" class="add-pattern-form">
            <select v-model="newPattern.type" class="filter-select">
              <option value="repo">Repository</option>
              <option value="branch">Branch</option>
              <option value="author">PR Author</option>
            </select>
            <input
              v-model="newPattern.pattern"
              class="text-input"
              placeholder="Regex pattern (e.g. dependabot/.*)"
              type="text"
            />
            <input
              v-model="newPattern.description"
              class="text-input"
              placeholder="Description (optional)"
              type="text"
            />
            <div class="form-actions">
              <button class="btn-primary" @click="addPattern(selectedFilter)">Add</button>
              <button class="btn-ghost" @click="addPatternOpen = false">Cancel</button>
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
              <button class="remove-btn" title="Remove pattern" @click="removePattern(selectedFilter, p.id)">✕</button>
            </div>
            <div v-if="!selectedFilter.patterns || selectedFilter.patterns.length === 0" class="empty-patterns">
              No patterns defined. Add a pattern to start filtering.
            </div>
          </div>
        </div>

        <!-- Test sandbox -->
        <div class="test-section">
          <h3>Test Filter</h3>
          <p class="test-desc">Simulate whether a repo, branch, or author would trigger this bot.</p>
          <div class="test-controls">
            <select v-model="testType" class="filter-select">
              <option value="repo">Repository</option>
              <option value="branch">Branch</option>
              <option value="author">Author</option>
            </select>
            <input
              v-model="testInput"
              class="text-input test-input"
              :placeholder="testType === 'repo' ? 'e.g. org/my-service' : testType === 'branch' ? 'e.g. dependabot/npm/lodash' : 'e.g. renovate[bot]'"
              type="text"
              @keydown.enter="runTest"
            />
            <button class="btn-primary" @click="runTest">Test</button>
          </div>
          <div v-if="testResults.length > 0" class="test-results">
            <div v-for="(result, idx) in testResults.slice(0, 5)" :key="idx" class="test-result-row">
              <span class="test-value">{{ result.type }}: <code>{{ result.input }}</code></span>
              <span class="test-verdict" :style="{ color: result.matchedBy?.includes('FIRES') ? 'var(--accent-green)' : 'var(--accent-amber)' }">
                {{ result.matchedBy }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="panel-placeholder">
        <p>Select a bot filter to view and edit its scope patterns.</p>
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
