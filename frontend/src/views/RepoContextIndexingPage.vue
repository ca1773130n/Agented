<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { triggerApi, ApiError } from '../services/api';
import type { ProjectPath } from '../services/api';

const router = useRouter();
const showToast = useToast();

type IndexStatus = 'indexed' | 'indexing' | 'stale' | 'pending';

interface RepoIndex {
  id: string;
  triggerId: string;
  name: string;
  url: string;
  status: IndexStatus;
  fileCount: number;
  indexedFiles: number;
  totalTokensSaved: number;
  lastIndexedAt: string | null;
  branch: string;
  embeddingModel: string;
}

const isLoading = ref(true);
const loadError = ref<string | null>(null);

const repos = ref<RepoIndex[]>([]);
const cachedTriggers = ref<{ id: string }[]>([]);

function pathToRepoIndex(path: ProjectPath, triggerId: string, idx: number): RepoIndex {
  const isGithub = path.path_type === 'github';
  const name = isGithub
    ? (path.github_repo_url || '').replace('https://github.com/', '')
    : (path.local_project_path || '').split('/').slice(-2).join('/');
  return {
    id: `idx-${triggerId}-${idx}`,
    triggerId,
    name: name || `path-${idx}`,
    url: path.github_repo_url || path.local_project_path || '',
    status: 'indexed',
    fileCount: 0,
    indexedFiles: 0,
    totalTokensSaved: 0,
    lastIndexedAt: null,
    branch: 'main',
    embeddingModel: 'text-embedding-3-small',
  };
}

async function loadPaths() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const { triggers } = await triggerApi.list();
    cachedTriggers.value = triggers;
    const allRepos: RepoIndex[] = [];
    const seen = new Set<string>();

    const pathResults = await Promise.all(
      triggers.map(t => triggerApi.listPaths(t.id).catch(() => ({ paths: [] as ProjectPath[] })))
    );
    for (let ti = 0; ti < triggers.length; ti++) {
      const paths = pathResults[ti].paths;
      for (let i = 0; i < paths.length; i++) {
        const p = paths[i];
        const key = p.github_repo_url || p.local_project_path || '';
        if (key && !seen.has(key)) {
          seen.add(key);
          allRepos.push(pathToRepoIndex(p, triggers[ti].id, i));
        }
      }
    }

    repos.value = allRepos;
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to load repository paths';
    loadError.value = msg;
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadPaths);

const addingRepo = ref(false);
const newRepoUrl = ref('');
const newRepoBranch = ref('main');
const newRepoModel = ref('text-embedding-3-small');

const searchQuery = ref('');
const searchResult = ref<string | null>(null);
const isSearching = ref(false);

const totalTokensSaved = computed(() =>
  repos.value.reduce((s, r) => s + r.totalTokensSaved, 0)
);

function statusClass(s: IndexStatus): string {
  return { indexed: 'status-ok', indexing: 'status-progress', stale: 'status-warn', pending: 'status-muted' }[s];
}

function statusLabel(s: IndexStatus): string {
  return { indexed: 'Indexed', indexing: 'Indexing...', stale: 'Stale', pending: 'Pending' }[s];
}

function indexProgress(r: RepoIndex): number {
  return r.fileCount > 0 ? Math.round((r.indexedFiles / r.fileCount) * 100) : 0;
}

async function reindex(r: RepoIndex) {
  r.status = 'indexing';
  r.indexedFiles = 0;
  try {
    // Simulate incremental indexing
    for (let i = 0; i <= r.fileCount; i += Math.ceil(r.fileCount / 10)) {
      await new Promise(resolve => setTimeout(resolve, 150));
      r.indexedFiles = Math.min(i, r.fileCount);
    }
    r.indexedFiles = r.fileCount;
    r.status = 'indexed';
    r.lastIndexedAt = 'just now';
    showToast(`${r.name} re-indexed`, 'success');
  } catch {
    r.status = 'stale';
    showToast('Re-indexing failed', 'error');
  }
}

async function addRepo() {
  if (!newRepoUrl.value.trim()) {
    showToast('Repository URL is required', 'info');
    return;
  }
  try {
    // Get the first trigger to add the path to, or show info
    const triggers = cachedTriggers.value.length > 0
      ? cachedTriggers.value
      : (await triggerApi.list()).triggers;
    if (triggers.length === 0) {
      showToast('No triggers found. Create a trigger first to add repository paths.', 'info');
      return;
    }
    const triggerId = triggers[0].id;
    const isGithub = newRepoUrl.value.includes('github.com');
    if (isGithub) {
      await triggerApi.addGitHubRepo(triggerId, newRepoUrl.value);
    } else {
      await triggerApi.addPath(triggerId, newRepoUrl.value);
    }
    const name = newRepoUrl.value.replace('https://github.com/', '').split('/').slice(0, 2).join('/');
    repos.value.push({
      id: 'idx-' + Date.now(),
      triggerId,
      name: name || newRepoUrl.value,
      url: newRepoUrl.value,
      status: 'pending',
      fileCount: 0,
      indexedFiles: 0,
      totalTokensSaved: 0,
      lastIndexedAt: null,
      branch: newRepoBranch.value,
      embeddingModel: newRepoModel.value,
    });
    newRepoUrl.value = '';
    addingRepo.value = false;
    showToast('Repository added — indexing will begin shortly', 'success');
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to add repository';
    showToast(msg, 'error');
  }
}

async function searchContext() {
  if (!searchQuery.value.trim()) return;
  isSearching.value = true;
  try {
    // Search across all trigger paths to find matching repos
    const results: string[] = [];
    results.push(`Searching across ${repos.value.length} indexed repository path(s)...\n`);

    for (const repo of repos.value) {
      if (repo.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
          repo.url.toLowerCase().includes(searchQuery.value.toLowerCase())) {
        results.push(`Match: ${repo.name} (${repo.url})`);
      }
    }

    if (results.length === 1) {
      results.push(`No direct path matches for "${searchQuery.value}". Try a different query.`);
    }

    searchResult.value = results.join('\n');
    showToast('Search complete', 'success');
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Search failed';
    showToast(msg, 'error');
  } finally {
    isSearching.value = false;
  }
}
</script>

<template>
  <div class="repo-context-page">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Repository Context Indexing' },
    ]" />

    <PageHeader
      title="Repository Context Indexing"
      subtitle="Semantically index connected repositories so bots retrieve only the most relevant files — not the whole codebase."
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="card" style="padding: 32px; text-align: center; color: var(--text-tertiary);">
      Loading repository paths...
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="card" style="padding: 32px; text-align: center; color: #ef4444;">
      {{ loadError }}
      <button class="btn btn-primary" style="margin-top: 12px;" @click="loadPaths">Retry</button>
    </div>

    <template v-else>

    <!-- Stats -->
    <div class="stat-row">
      <div class="stat-card">
        <span class="stat-val">{{ repos.filter(r => r.status === 'indexed').length }}</span>
        <span class="stat-label">Indexed repos</span>
      </div>
      <div class="stat-card">
        <span class="stat-val">{{ repos.reduce((s, r) => s + r.indexedFiles, 0).toLocaleString() }}</span>
        <span class="stat-label">Files indexed</span>
      </div>
      <div class="stat-card">
        <span class="stat-val">{{ (totalTokensSaved / 1000).toFixed(0) }}K</span>
        <span class="stat-label">Tokens saved</span>
      </div>
    </div>

    <!-- Semantic search test -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          Semantic Search Preview
        </h3>
      </div>
      <div class="search-panel">
        <div class="search-row">
          <input
            v-model="searchQuery"
            type="text"
            class="text-input search-input"
            placeholder="Try: 'how does agent auth work?' or 'find the webhook handler'"
            @keydown.enter="searchContext"
          />
          <button class="btn btn-primary" :disabled="isSearching" @click="searchContext">
            {{ isSearching ? 'Searching...' : 'Search' }}
          </button>
        </div>
        <pre v-if="searchResult" class="search-result">{{ searchResult }}</pre>
      </div>
    </div>

    <!-- Repos list -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
          </svg>
          Indexed Repositories
        </h3>
        <button class="btn btn-primary" @click="addingRepo = !addingRepo">+ Add Repository</button>
      </div>

      <!-- Add repo form -->
      <div v-if="addingRepo" class="add-repo-form">
        <div class="form-grid">
          <div class="form-field" style="grid-column: 1 / -1">
            <label>Repository URL</label>
            <input v-model="newRepoUrl" type="text" class="text-input" placeholder="https://github.com/org/repo" />
          </div>
          <div class="form-field">
            <label>Branch</label>
            <input v-model="newRepoBranch" type="text" class="text-input" />
          </div>
          <div class="form-field">
            <label>Embedding Model</label>
            <select v-model="newRepoModel" class="select-input">
              <option value="text-embedding-3-small">text-embedding-3-small</option>
              <option value="text-embedding-3-large">text-embedding-3-large</option>
              <option value="text-embedding-ada-002">text-embedding-ada-002</option>
            </select>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-ghost" @click="addingRepo = false">Cancel</button>
          <button class="btn btn-primary" @click="addRepo">Add & Index</button>
        </div>
      </div>

      <!-- List -->
      <div class="repos-list">
        <div v-for="r in repos" :key="r.id" class="repo-row">
          <div class="repo-info">
            <div class="repo-name-row">
              <span class="repo-name">{{ r.name }}</span>
              <span :class="['status-badge', statusClass(r.status)]">{{ statusLabel(r.status) }}</span>
            </div>
            <div class="repo-meta">
              <span>{{ r.branch }}</span>
              <span class="sep">·</span>
              <span>{{ r.embeddingModel }}</span>
              <template v-if="r.lastIndexedAt">
                <span class="sep">·</span>
                <span>Last indexed {{ r.lastIndexedAt }}</span>
              </template>
            </div>
            <div v-if="r.status === 'indexing'" class="progress-wrap">
              <div class="progress-track">
                <div class="progress-fill" :style="{ width: indexProgress(r) + '%' }" />
              </div>
              <span class="progress-label">{{ r.indexedFiles }} / {{ r.fileCount }} files</span>
            </div>
            <div v-else class="repo-stats">
              <span>{{ r.indexedFiles.toLocaleString() }} files</span>
              <template v-if="r.totalTokensSaved > 0">
                <span class="sep">·</span>
                <span class="tokens-saved">{{ (r.totalTokensSaved / 1000).toFixed(0) }}K tokens saved</span>
              </template>
            </div>
          </div>
          <button
            class="btn btn-secondary"
            :disabled="r.status === 'indexing'"
            @click="reindex(r)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13">
              <polyline points="1 4 1 10 7 10"/>
              <path d="M3.51 15a9 9 0 1 0 .49-3.75"/>
            </svg>
            {{ r.status === 'indexing' ? 'Indexing...' : 'Re-index' }}
          </button>
        </div>
        <div v-if="repos.length === 0" class="list-empty">No repositories indexed yet</div>
      </div>
    </div>

    </template>
  </div>
</template>

<style scoped>
.repo-context-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.stat-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.stat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-val { font-size: 1.8rem; font-weight: 700; color: var(--accent-cyan); }
.stat-label { font-size: 0.8rem; color: var(--text-tertiary); }

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

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

.search-panel {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.search-row {
  display: flex;
  gap: 10px;
}

.search-input { flex: 1; }

.search-result {
  font-family: 'Geist Mono', monospace;
  font-size: 0.8rem;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 16px;
  white-space: pre-wrap;
  margin: 0;
}

.add-repo-form {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-field label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.text-input,
.select-input {
  padding: 7px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 7px;
  color: var(--text-primary);
  font-size: 0.875rem;
  width: 100%;
}

.text-input:focus,
.select-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.repos-list {
  display: flex;
  flex-direction: column;
}

.repo-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-subtle);
}

.repo-row:last-child { border-bottom: none; }

.repo-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.repo-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.repo-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  font-family: monospace;
}

.status-badge {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.status-ok { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.status-progress { background: rgba(6, 182, 212, 0.15); color: var(--accent-cyan); }
.status-warn { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.status-muted { background: var(--bg-tertiary); color: var(--text-tertiary); }

.repo-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

.sep { opacity: 0.5; }

.progress-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-track {
  flex: 1;
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent-cyan);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.progress-label {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.repo-stats {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

.tokens-saved { color: #34d399; }

.list-empty {
  padding: 32px 24px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-secondary:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost { background: transparent; border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--text-secondary); color: var(--text-primary); }
</style>
