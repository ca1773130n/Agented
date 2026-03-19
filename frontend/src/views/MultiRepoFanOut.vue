<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { triggerApi } from '../services/api';
import type { Trigger, ProjectPath } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
const showToast = useToast();

// Loading state
const isLoadingTriggers = ref(true);
const isLoadingPaths = ref(false);
const loadError = ref<string | null>(null);

// Data from API
const triggers = ref<Trigger[]>([]);
const selectedTriggerId = ref('');
const paths = ref<ProjectPath[]>([]);

// New repo form
const newRepoUrl = ref('');
const isAdding = ref(false);
const isRemoving = ref<number | null>(null);

// Test
const isTesting = ref(false);
const testResult = ref<string | null>(null);

async function loadTriggers() {
  isLoadingTriggers.value = true;
  loadError.value = null;
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers ?? [];
    if (triggers.value.length > 0) {
      selectedTriggerId.value = triggers.value[0].id;
    }
  } catch (err: unknown) {
    loadError.value = err instanceof Error ? err.message : 'Failed to load triggers';
  } finally {
    isLoadingTriggers.value = false;
  }
}

async function loadPaths() {
  if (!selectedTriggerId.value) {
    paths.value = [];
    return;
  }
  isLoadingPaths.value = true;
  try {
    const res = await triggerApi.listPaths(selectedTriggerId.value);
    paths.value = res.paths ?? [];
  } catch {
    paths.value = [];
  } finally {
    isLoadingPaths.value = false;
  }
}

watch(selectedTriggerId, () => {
  loadPaths();
  testResult.value = null;
});

async function addRepo() {
  const url = newRepoUrl.value.trim();
  if (!url) {
    showToast('Repository URL is required', 'info');
    return;
  }
  if (!selectedTriggerId.value) {
    showToast('Select a trigger first', 'info');
    return;
  }
  isAdding.value = true;
  try {
    // Determine if it looks like a GitHub URL or a local path
    if (url.includes('github.com') || url.match(/^[\w-]+\/[\w.-]+$/)) {
      await triggerApi.addGitHubRepo(selectedTriggerId.value, url);
    } else {
      await triggerApi.addPath(selectedTriggerId.value, url);
    }
    showToast('Repository added', 'success');
    newRepoUrl.value = '';
    await loadPaths();
  } catch (err: unknown) {
    showToast(err instanceof Error ? err.message : 'Failed to add repository', 'error');
  } finally {
    isAdding.value = false;
  }
}

async function removePath(path: ProjectPath) {
  if (!selectedTriggerId.value) return;
  isRemoving.value = path.id;
  try {
    if (path.github_repo_url) {
      await triggerApi.removeGitHubRepo(selectedTriggerId.value, path.github_repo_url);
    } else {
      await triggerApi.removePath(selectedTriggerId.value, path.local_project_path);
    }
    showToast('Repository removed', 'success');
    await loadPaths();
  } catch (err: unknown) {
    showToast(err instanceof Error ? err.message : 'Failed to remove', 'error');
  } finally {
    isRemoving.value = null;
  }
}

async function handleTest() {
  if (!selectedTriggerId.value) {
    showToast('Select a trigger first', 'info');
    return;
  }
  isTesting.value = true;
  testResult.value = null;
  try {
    const res = await triggerApi.previewPromptFull(selectedTriggerId.value, {});
    testResult.value = `Prompt preview rendered successfully. ${res.unresolved_placeholders?.length ? `Unresolved placeholders: ${res.unresolved_placeholders.join(', ')}` : 'All placeholders resolved.'}`;
    showToast('Fan-out test complete', 'success');
  } catch (err: unknown) {
    testResult.value = err instanceof Error ? err.message : 'Test failed';
    showToast('Test failed', 'error');
  } finally {
    isTesting.value = false;
  }
}

function displayPath(p: ProjectPath): string {
  if (p.github_repo_url) return p.github_repo_url;
  if (p.project_name) return `${p.project_name} (${p.local_project_path})`;
  return p.local_project_path;
}

function pathTypeLabel(p: ProjectPath): string {
  if (p.path_type === 'github') return 'GitHub';
  if (p.path_type === 'project') return 'Project';
  return 'Local';
}

const selectedTriggerName = () => {
  const t = triggers.value.find(t => t.id === selectedTriggerId.value);
  return t?.name ?? '';
};

onMounted(loadTriggers);
</script>

<template>
  <div class="multi-repo">

    <PageHeader title="Multi-Repo Fan-Out" subtitle="Configure a single trigger watching multiple repos with per-repo bot routing.">
      <template #actions>
        <button class="btn btn-secondary" :disabled="isTesting || !selectedTriggerId" @click="handleTest">
          <svg v-if="isTesting" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
          {{ isTesting ? 'Testing...' : 'Test Fan-Out' }}
        </button>
      </template>
    </PageHeader>

    <!-- Loading state -->
    <div v-if="isLoadingTriggers" class="card loading-card">
      <div class="loading-content">Loading triggers...</div>
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="card error-card">
      <div class="error-content">
        <span>{{ loadError }}</span>
        <button class="btn btn-secondary" @click="loadTriggers">Retry</button>
      </div>
    </div>

    <template v-else>
      <div class="card trigger-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            Base Trigger
          </h3>
        </div>
        <div class="trigger-body">
          <div class="field-group">
            <label class="field-label">Select Trigger to Fan-Out</label>
            <select v-model="selectedTriggerId" class="select-input">
              <option value="">-- Select trigger --</option>
              <option v-for="t in triggers" :key="t.id" :value="t.id">{{ t.name }}</option>
            </select>
          </div>
          <div class="trigger-info">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14" style="color: var(--accent-cyan)">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 8v4l3 3"/>
            </svg>
            When this trigger fires, the payload will be routed to each matching repo's bot based on the paths below.
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>
              <path d="M18 9a9 9 0 0 1-9 9"/>
            </svg>
            Fan-Out Paths
          </h3>
          <span class="card-badge">{{ paths.length }} paths</span>
        </div>

        <!-- Add new path -->
        <div class="add-mapping">
          <div class="add-row">
            <input
              v-model="newRepoUrl"
              type="text"
              class="text-input"
              placeholder="GitHub URL (https://github.com/org/repo) or local path"
              :disabled="!selectedTriggerId"
              @keyup.enter="addRepo"
            />
            <button class="btn btn-primary" :disabled="isAdding || !selectedTriggerId || !newRepoUrl.trim()" @click="addRepo">
              {{ isAdding ? 'Adding...' : 'Add' }}
            </button>
          </div>
        </div>

        <!-- Loading paths indicator -->
        <div v-if="isLoadingPaths" class="mappings-loading">Loading paths...</div>

        <div v-else class="mappings-list">
          <div v-for="p in paths" :key="p.id" class="mapping-row">
            <div class="mapping-repo">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14" style="color: var(--text-tertiary)">
                <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
              </svg>
              <span class="repo-name">{{ displayPath(p) }}</span>
            </div>
            <div class="mapping-type">
              <span class="type-tag">{{ pathTypeLabel(p) }}</span>
            </div>
            <div v-if="p.project_name" class="mapping-project">
              <span class="project-name">{{ p.project_name }}</span>
            </div>
            <div class="mapping-actions">
              <button
                class="btn-icon-sm"
                :disabled="isRemoving === p.id"
                @click="removePath(p)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          </div>
          <div v-if="paths.length === 0 && !isLoadingPaths" class="mappings-empty">
            No paths configured for {{ selectedTriggerName() || 'this trigger' }}. Add a repository above.
          </div>
        </div>
      </div>

      <!-- Test result -->
      <div v-if="testResult" class="card test-result-card">
        <div class="card-header">
          <h3>Test Result</h3>
        </div>
        <div class="test-result-body">{{ testResult }}</div>
      </div>

      <div class="card overview-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 8v4l3 3"/>
            </svg>
            Fan-Out Overview
          </h3>
        </div>
        <div class="overview-body">
          <div class="overview-stats">
            <div class="ov-stat">
              <span class="ov-num">{{ paths.length }}</span>
              <span class="ov-lbl">Total paths</span>
            </div>
            <div class="ov-stat">
              <span class="ov-num" style="color: #34d399">{{ paths.filter(p => p.path_type === 'github').length }}</span>
              <span class="ov-lbl">GitHub repos</span>
            </div>
            <div class="ov-stat">
              <span class="ov-num">{{ paths.filter(p => p.path_type === 'local').length }}</span>
              <span class="ov-lbl">Local paths</span>
            </div>
            <div class="ov-stat">
              <span class="ov-num">{{ paths.filter(p => p.path_type === 'project').length }}</span>
              <span class="ov-lbl">Projects</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.multi-repo {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.loading-card, .error-card { padding: 32px 24px; }
.loading-content { text-align: center; color: var(--text-tertiary); font-size: 0.875rem; }
.error-content { display: flex; align-items: center; justify-content: center; gap: 12px; color: #ef4444; font-size: 0.875rem; }

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.trigger-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 0.83rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.select-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  max-width: 400px;
}

.select-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.trigger-info {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.83rem;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 10px 14px;
  border-radius: 8px;
}

.add-mapping {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--bg-tertiary);
}

.add-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.text-input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;
  font-family: monospace;
}

.text-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.text-input:disabled {
  opacity: 0.4;
}

.mappings-loading {
  padding: 24px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.82rem;
}

.mappings-list {
  display: flex;
  flex-direction: column;
}

.mapping-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}

.mapping-row:hover { background: var(--bg-tertiary); }
.mapping-row:last-child { border-bottom: none; }

.mapping-repo {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.repo-name {
  font-family: monospace;
  font-size: 0.85rem;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mapping-type { flex-shrink: 0; }

.type-tag {
  font-size: 0.7rem;
  padding: 2px 7px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 3px;
  color: var(--text-tertiary);
}

.mapping-project { flex-shrink: 0; }
.project-name {
  font-size: 0.78rem;
  color: var(--accent-cyan);
}

.mapping-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.mappings-empty {
  padding: 32px 24px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

.test-result-card .test-result-body {
  padding: 16px 24px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.overview-body { padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }

.overview-stats {
  display: flex;
  gap: 32px;
}

.ov-stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ov-num {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
}

.ov-lbl {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.btn-icon-sm {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.1s;
}

.btn-icon-sm:hover { border-color: #ef4444; color: #ef4444; }
.btn-icon-sm:disabled { opacity: 0.4; cursor: not-allowed; }

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--text-primary); }
.btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
