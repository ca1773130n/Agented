<script setup lang="ts">
import { ref, computed } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();

type FilterMode = 'allowlist' | 'denylist';
type PatternType = 'repo' | 'branch' | 'author';

interface ScopeFilter {
  id: string;
  botId: string;
  botName: string;
  mode: FilterMode;
  patterns: PatternRule[];
  enabled: boolean;
  lastModified: string;
}

interface PatternRule {
  id: string;
  type: PatternType;
  pattern: string;
  description: string;
}

interface TestResult {
  input: string;
  type: PatternType;
  matched: boolean;
  matchedBy?: string;
}

const filters = ref<ScopeFilter[]>([
  {
    id: 'sf-001',
    botId: 'bot-pr-review',
    botName: 'PR Review Bot',
    mode: 'denylist',
    enabled: true,
    lastModified: '2026-03-01T00:00:00Z',
    patterns: [
      { id: 'p-001', type: 'repo', pattern: '.*-prototype$', description: 'Skip prototype repos' },
      { id: 'p-002', type: 'repo', pattern: '.*-archive$', description: 'Skip archived repos' },
      { id: 'p-003', type: 'branch', pattern: 'dependabot/.*', description: 'Skip Dependabot PRs' },
      { id: 'p-004', type: 'author', pattern: 'renovate\\[bot\\]', description: 'Skip Renovate bot PRs' },
      { id: 'p-005', type: 'author', pattern: 'github-actions\\[bot\\]', description: 'Skip GH Actions bot PRs' },
    ],
  },
  {
    id: 'sf-002',
    botId: 'bot-security',
    botName: 'Security Audit Bot',
    mode: 'allowlist',
    enabled: true,
    lastModified: '2026-02-15T00:00:00Z',
    patterns: [
      { id: 'p-006', type: 'repo', pattern: 'org/backend-.*', description: 'Only backend repos' },
      { id: 'p-007', type: 'repo', pattern: 'org/api-.*', description: 'Only API repos' },
      { id: 'p-008', type: 'branch', pattern: 'main|master|release/.*', description: 'Only production branches' },
    ],
  },
]);

const selectedFilterId = ref<string | null>(null);
const newPattern = ref<Partial<PatternRule>>({ type: 'repo', pattern: '', description: '' });
const testInput = ref('');
const testType = ref<PatternType>('repo');
const testResults = ref<TestResult[]>([]);
const addPatternOpen = ref(false);

const selectedFilter = computed(() => filters.value.find((f) => f.id === selectedFilterId.value));

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

function removePattern(filter: ScopeFilter, patternId: string) {
  filter.patterns = filter.patterns.filter((p) => p.id !== patternId);
  filter.lastModified = new Date().toISOString();
  showToast('Pattern removed', 'info');
}

function addPattern(filter: ScopeFilter) {
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
  filter.patterns.push({
    id: `p-${Date.now()}`,
    type: newPattern.value.type as PatternType,
    pattern: newPattern.value.pattern,
    description: newPattern.value.description || '',
  });
  filter.lastModified = new Date().toISOString();
  newPattern.value = { type: 'repo', pattern: '', description: '' };
  addPatternOpen.value = false;
  showToast('Pattern added', 'success');
}

function toggleFilter(filter: ScopeFilter) {
  filter.enabled = !filter.enabled;
  showToast(`Scope filter ${filter.enabled ? 'enabled' : 'disabled'}`, 'info');
}

function toggleMode(filter: ScopeFilter) {
  filter.mode = filter.mode === 'allowlist' ? 'denylist' : 'allowlist';
  filter.lastModified = new Date().toISOString();
  showToast(`Switched to ${modeLabel(filter.mode)}`, 'info');
}

function runTest() {
  if (!selectedFilter.value || !testInput.value.trim()) {
    showToast('Enter a test value first', 'info');
    return;
  }
  const filter = selectedFilter.value;
  const relevant = filter.patterns.filter((p) => p.type === testType.value);
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
  testResults.value.unshift({
    input: testInput.value,
    type: testType.value,
    matched,
    matchedBy: matched ? `${fires} — matched by: ${matchedBy}` : fires,
  });
  testInput.value = '';
}

const patternCount = computed(() =>
  filters.value.reduce((sum, f) => sum + f.patterns.length, 0)
);
</script>

<template>
  <div class="page-container">
    <AppBreadcrumb :items="[{ label: 'Bots' }, { label: 'Repository Scope Filters' }]" />
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

    <div class="main-layout">
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
            <span class="bot-name">{{ filter.botName }}</span>
            <span class="mode-badge" :style="{ background: modeColor(filter.mode) + '22', color: modeColor(filter.mode) }">
              {{ modeLabel(filter.mode) }}
            </span>
            <span class="enabled-badge" :class="{ active: filter.enabled }">
              {{ filter.enabled ? 'Active' : 'Disabled' }}
            </span>
          </div>
          <div class="pattern-summary">
            <span v-for="(count, type) in { repo: filter.patterns.filter((p) => p.type === 'repo').length, branch: filter.patterns.filter((p) => p.type === 'branch').length, author: filter.patterns.filter((p) => p.type === 'author').length }" :key="type">
              <span v-if="(count as number) > 0" class="type-chip">
                {{ typeIcon(type as PatternType) }} {{ count }} {{ type }}
              </span>
            </span>
          </div>
          <div class="filter-meta">Last modified {{ new Date(filter.lastModified).toLocaleDateString() }}</div>
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
            <div v-if="selectedFilter.patterns.length === 0" class="empty-patterns">
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
