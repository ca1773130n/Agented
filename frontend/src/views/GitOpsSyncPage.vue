<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { ApiError } from '../services/api';
import { gitopsApi } from '../services/api';
import type { GitOpsRepo, SyncLog } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const repos = ref<GitOpsRepo[]>([]);
const selectedRepoId = ref<string | null>(null);
const syncLogs = ref<SyncLog[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);

const showAddForm = ref(false);
const newRepoName = ref('');
const newRepoUrl = ref('');
const newBranch = ref('main');
const newConfigPath = ref('.agented/');
const isCreating = ref(false);
const isSyncing = ref(false);
const deletingId = ref<string | null>(null);

const selectedRepo = computed(() =>
  repos.value.find(r => r.id === selectedRepoId.value) ?? null
);

async function loadRepos() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await gitopsApi.listRepos();
    repos.value = Array.isArray(data) ? data : [];
    if (repos.value.length > 0 && !selectedRepoId.value) {
      selectedRepoId.value = repos.value[0].id;
      await loadLogs(repos.value[0].id);
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load GitOps repos';
    loadError.value = message;
  } finally {
    isLoading.value = false;
  }
}

async function loadLogs(repoId: string) {
  try {
    const data = await gitopsApi.getSyncLogs(repoId);
    syncLogs.value = Array.isArray(data) ? data : [];
  } catch {
    syncLogs.value = [];
  }
}

async function selectRepo(repoId: string) {
  selectedRepoId.value = repoId;
  await loadLogs(repoId);
}

async function handleCreate() {
  if (!newRepoName.value.trim() || !newRepoUrl.value.trim()) {
    showToast('Name and repository URL are required', 'info');
    return;
  }
  isCreating.value = true;
  try {
    const repo = await gitopsApi.createRepo({
      name: newRepoName.value.trim(),
      repo_url: newRepoUrl.value.trim(),
      branch: newBranch.value || 'main',
      config_path: newConfigPath.value || '.agented/',
    });
    repos.value.unshift(repo);
    selectedRepoId.value = repo.id;
    newRepoName.value = '';
    newRepoUrl.value = '';
    newBranch.value = 'main';
    newConfigPath.value = '.agented/';
    showAddForm.value = false;
    showToast('Repository added', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to create repo';
    showToast(message, 'error');
  } finally {
    isCreating.value = false;
  }
}

async function handleSync(dryRun = false) {
  if (!selectedRepoId.value) return;
  isSyncing.value = true;
  try {
    const result = await gitopsApi.triggerSync(selectedRepoId.value, dryRun);
    showToast(dryRun ? 'Dry run completed' : 'Sync completed', 'success');
    if (result.status) {
      // Refresh repo and logs
      await Promise.all([loadRepos(), loadLogs(selectedRepoId.value!)]);
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Sync failed';
    showToast(message, 'error');
  } finally {
    isSyncing.value = false;
  }
}

async function handleDelete(repo: GitOpsRepo) {
  deletingId.value = repo.id;
  try {
    await gitopsApi.deleteRepo(repo.id);
    repos.value = repos.value.filter(r => r.id !== repo.id);
    if (selectedRepoId.value === repo.id) {
      selectedRepoId.value = repos.value.length > 0 ? repos.value[0].id : null;
      if (selectedRepoId.value) await loadLogs(selectedRepoId.value);
      else syncLogs.value = [];
    }
    showToast('Repository removed', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to delete repo';
    showToast(message, 'error');
  } finally {
    deletingId.value = null;
  }
}

async function toggleEnabled(repo: GitOpsRepo) {
  const newEnabled = !repo.enabled;
  try {
    await gitopsApi.updateRepo(repo.id, { enabled: newEnabled });
    repo.enabled = newEnabled ? 1 : 0;
    showToast(`Repository ${newEnabled ? 'enabled' : 'disabled'}`, 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update repo';
    showToast(message, 'error');
  }
}

function statusColor(status: string | null): string {
  if (!status) return '#6b7280';
  const map: Record<string, string> = { success: '#34d399', error: '#ef4444', running: '#f59e0b' };
  return map[status] ?? '#6b7280';
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  return new Date(dateStr).toLocaleString();
}

onMounted(loadRepos);
</script>

<template>
  <div class="gitops">
    <AppBreadcrumb :items="[
      { label: 'Settings', action: () => router.push({ name: 'settings' }) },
      { label: 'GitOps Sync' },
    ]" />

    <PageHeader
      title="GitOps Repository Sync"
      subtitle="Configure Git repositories for syncing bot and agent configurations."
    >
      <template #actions>
        <button class="btn btn-primary" @click="showAddForm = !showAddForm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Add Repository
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading GitOps configuration..." />

    <div v-else-if="loadError" class="card error-card">
      <div class="error-inner">
        <p>{{ loadError }}</p>
        <button class="btn btn-ghost" @click="loadRepos">Retry</button>
      </div>
    </div>

    <template v-else>
      <!-- Add Form -->
      <div v-if="showAddForm" class="card create-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
              <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
            </svg>
            Add Repository
          </h3>
        </div>
        <div class="form-body">
          <div class="field-row">
            <div class="field">
              <label class="field-label">Name <span class="required">*</span></label>
              <input v-model="newRepoName" type="text" class="input" placeholder="my-project-config" />
            </div>
            <div class="field">
              <label class="field-label">Repository URL <span class="required">*</span></label>
              <input v-model="newRepoUrl" type="text" class="input" placeholder="https://github.com/org/repo.git" />
            </div>
          </div>
          <div class="field-row">
            <div class="field">
              <label class="field-label">Branch</label>
              <input v-model="newBranch" type="text" class="input" placeholder="main" />
            </div>
            <div class="field">
              <label class="field-label">Config Path</label>
              <input v-model="newConfigPath" type="text" class="input" placeholder=".agented/" />
            </div>
          </div>
          <div class="form-actions">
            <button class="btn btn-ghost" @click="showAddForm = false">Cancel</button>
            <button class="btn btn-primary" :disabled="isCreating || !newRepoName.trim() || !newRepoUrl.trim()" @click="handleCreate">
              {{ isCreating ? 'Adding...' : 'Add Repository' }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="repos.length === 0 && !showAddForm" class="card empty-card">
        <div class="empty-inner">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="40" height="40" style="opacity: 0.3; color: var(--text-tertiary)">
            <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
          </svg>
          <p>No GitOps repositories configured yet.</p>
        </div>
      </div>

      <div v-else class="layout">
        <!-- Repo list -->
        <div class="side-col">
          <div class="card">
            <div class="card-header">
              <h3>Repositories</h3>
              <span class="card-badge">{{ repos.length }}</span>
            </div>
            <div class="repo-list">
              <div
                v-for="repo in repos"
                :key="repo.id"
                class="repo-item"
                :class="{ selected: selectedRepoId === repo.id }"
                @click="selectRepo(repo.id)"
              >
                <div class="repo-item-info">
                  <div class="repo-item-name">{{ repo.name }}</div>
                  <div class="repo-item-url">{{ repo.repo_url }}</div>
                  <div class="repo-item-meta">
                    <span class="status-dot" :style="{ background: statusColor(repo.last_sync_status) }" />
                    <span>{{ repo.last_sync_status || 'Not synced' }}</span>
                    <span class="meta-sep">&middot;</span>
                    <span>{{ repo.branch }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Selected repo detail -->
        <div class="main-col">
          <template v-if="selectedRepo">
            <!-- Status banner -->
            <div class="status-banner" :style="{ borderColor: statusColor(selectedRepo.last_sync_status) }">
              <div class="status-dot" :style="{ background: statusColor(selectedRepo.last_sync_status) }" />
              <span class="status-label" :style="{ color: statusColor(selectedRepo.last_sync_status) }">
                {{ selectedRepo.last_sync_status || 'Not synced' }}
              </span>
              <span v-if="selectedRepo.last_sync_at" class="status-time">Last synced {{ formatDate(selectedRepo.last_sync_at) }}</span>
              <div class="banner-actions">
                <button
                  class="btn btn-sm btn-ghost"
                  :disabled="isSyncing"
                  @click="handleSync(true)"
                >
                  Dry Run
                </button>
                <button
                  class="btn btn-primary btn-sm"
                  :disabled="isSyncing"
                  @click="handleSync(false)"
                >
                  <svg v-if="isSyncing" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                  </svg>
                  <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                    <polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/>
                    <polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>
                  </svg>
                  {{ isSyncing ? 'Syncing...' : 'Sync Now' }}
                </button>
              </div>
            </div>

            <!-- Repo details -->
            <div class="card">
              <div class="card-header">
                <h3>{{ selectedRepo.name }}</h3>
                <div class="header-actions">
                  <button
                    :class="['toggle-btn', { active: !!selectedRepo.enabled }]"
                    @click="toggleEnabled(selectedRepo)"
                  >
                    <span class="toggle-thumb" />
                  </button>
                  <button class="btn btn-sm btn-delete" :disabled="deletingId === selectedRepo.id" @click="handleDelete(selectedRepo)">
                    {{ deletingId === selectedRepo.id ? '...' : 'Delete' }}
                  </button>
                </div>
              </div>
              <div class="detail-grid">
                <div class="detail-item">
                  <span class="detail-label">Repository URL</span>
                  <span class="detail-value">{{ selectedRepo.repo_url }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Branch</span>
                  <span class="detail-value">{{ selectedRepo.branch }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Config Path</span>
                  <span class="detail-value">{{ selectedRepo.config_path }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Poll Interval</span>
                  <span class="detail-value">{{ selectedRepo.poll_interval_seconds }}s</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">Last Sync SHA</span>
                  <span class="detail-value mono">{{ selectedRepo.last_sync_sha || 'None' }}</span>
                </div>
              </div>
            </div>

            <!-- Sync Log -->
            <div class="card">
              <div class="card-header">
                <h3>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                  </svg>
                  Sync History
                </h3>
              </div>
              <div v-if="syncLogs.length === 0" class="list-empty">No sync history yet.</div>
              <div v-else class="log-list">
                <div v-for="log in syncLogs" :key="log.id" class="log-entry">
                  <span class="log-time">{{ formatDate(log.created_at) }}</span>
                  <span :class="['log-icon', `log-${log.status}`]">
                    {{ log.status === 'success' ? '&#x2713;' : log.status === 'error' ? '&#x2717;' : '~' }}
                  </span>
                  <span class="log-action">
                    {{ log.changes_summary || log.error_message || log.status }}
                    <span v-if="log.dry_run" class="dry-run-badge">dry run</span>
                  </span>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.gitops {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.35s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px;
  align-items: start;
}

.main-col, .side-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

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
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  padding: 3px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.create-card { border-color: var(--accent-cyan); }

.error-card, .empty-card { padding: 48px; }

.error-inner, .empty-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.error-inner p, .empty-inner p {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  background: var(--bg-secondary);
  border: 1px solid;
  border-radius: 10px;
  flex-wrap: wrap;
}

.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.status-label { font-size: 0.85rem; font-weight: 600; text-transform: capitalize; }
.status-time { font-size: 0.78rem; color: var(--text-tertiary); }
.banner-actions { margin-left: auto; display: flex; gap: 8px; }

.repo-list { display: flex; flex-direction: column; }

.repo-item {
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background 0.1s;
}

.repo-item:hover { background: var(--bg-tertiary); }
.repo-item:last-child { border-bottom: none; }
.repo-item.selected { background: var(--bg-tertiary); border-left: 3px solid var(--accent-cyan); }

.repo-item-name { font-size: 0.875rem; font-weight: 600; color: var(--text-primary); }
.repo-item-url { font-size: 0.75rem; color: var(--text-tertiary); margin-top: 2px; word-break: break-all; }

.repo-item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-top: 6px;
}

.meta-sep { opacity: 0.5; }

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
}

.detail-item {
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-item:nth-last-child(-n+2) { border-bottom: none; }

.detail-label { font-size: 0.72rem; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
.detail-value { font-size: 0.85rem; color: var(--text-primary); word-break: break-all; }
.detail-value.mono { font-family: 'Geist Mono', monospace; font-size: 0.78rem; color: var(--accent-cyan); }

.form-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.field-label { font-size: 0.8rem; font-weight: 500; color: var(--text-secondary); }
.required { color: #ef4444; }
.form-actions { display: flex; gap: 10px; justify-content: flex-end; }

.input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.input:focus { outline: none; border-color: var(--accent-cyan); }

.list-empty {
  padding: 32px 20px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

.log-list { display: flex; flex-direction: column; }

.log-entry {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.82rem;
}

.log-entry:last-child { border-bottom: none; }
.log-time { font-family: 'Geist Mono', monospace; color: var(--text-tertiary); font-size: 0.75rem; white-space: nowrap; }

.log-icon {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 700;
  flex-shrink: 0;
}

.log-success { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.log-error { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.log-running { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.log-action { color: var(--text-secondary); }

.dry-run-badge {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 1px 5px;
  background: rgba(6, 182, 212, 0.12);
  color: var(--accent-cyan);
  border-radius: 3px;
  text-transform: uppercase;
  margin-left: 6px;
}

.toggle-btn {
  position: relative;
  width: 44px;
  height: 24px;
  border-radius: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
}

.toggle-btn.active { background: var(--accent-cyan); border-color: var(--accent-cyan); }

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
}

.toggle-btn.active .toggle-thumb { transform: translateX(20px); }

.btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 6px 12px; font-size: 0.8rem; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-ghost { padding: 8px 14px; background: transparent; border: 1px solid var(--border-default); color: var(--text-secondary); border-radius: 8px; }
.btn-ghost:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--text-primary); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-delete { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-tertiary); }
.btn-delete:hover:not(:disabled) { border-color: #ef4444; color: #ef4444; }
.btn-delete:disabled { opacity: 0.4; cursor: not-allowed; }

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
}
</style>
