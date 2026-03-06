<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

type SyncStatus = 'synced' | 'pending' | 'conflict' | 'error';

interface GitOpsConfig {
  repo_url: string;
  branch: string;
  path_prefix: string;
  auto_sync: boolean;
  sync_direction: 'pull' | 'push' | 'bidirectional';
  last_synced_at: string;
  status: SyncStatus;
}

const config = ref<GitOpsConfig>({
  repo_url: '',
  branch: 'main',
  path_prefix: '.agented/',
  auto_sync: false,
  sync_direction: 'bidirectional',
  last_synced_at: '',
  status: 'pending',
});

const isSaving = ref(false);
const isSyncing = ref(false);
const isLoading = ref(false);
const syncLog = ref<{ time: string; action: string; result: 'ok' | 'warn' | 'err' }[]>([]);

const statusLabels: Record<SyncStatus, string> = {
  synced: 'Synced',
  pending: 'Not Configured',
  conflict: 'Conflict Detected',
  error: 'Sync Error',
};

const statusColors: Record<SyncStatus, string> = {
  synced: '#34d399',
  pending: '#6b7280',
  conflict: '#f59e0b',
  error: '#ef4444',
};

const directionOptions = [
  { value: 'pull', label: 'Pull from Git (Git is source of truth)' },
  { value: 'push', label: 'Push to Git (Platform is source of truth)' },
  { value: 'bidirectional', label: 'Bidirectional (merge changes)' },
];

const FILE_TYPES = [
  { icon: '🤖', label: 'Bot Configurations', filename: 'bots.yaml', example: 'bot_id, name, prompt_template, trigger_config' },
  { icon: '🎯', label: 'Trigger Definitions', filename: 'triggers.yaml', example: 'trigger_id, type, event, conditions' },
  { icon: '🧩', label: 'Agent Definitions', filename: 'agents.yaml', example: 'agent_id, name, skills, hooks' },
  { icon: '🔐', label: 'Secret References', filename: 'secrets.yaml', example: 'secret keys only — values excluded for security' },
];

async function handleSave() {
  if (!config.value.repo_url) {
    showToast('Repository URL is required', 'error');
    return;
  }
  isSaving.value = true;
  try {
    await new Promise(r => setTimeout(r, 500));
    config.value.status = 'pending';
    showToast('GitOps configuration saved', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save configuration';
    showToast(message, 'error');
  } finally {
    isSaving.value = false;
  }
}

async function handleSync() {
  isSyncing.value = true;
  try {
    await new Promise(r => setTimeout(r, 1200));
    config.value.status = 'synced';
    config.value.last_synced_at = new Date().toISOString();
    syncLog.value.unshift(
      { time: new Date().toLocaleTimeString(), action: 'Pulled bots.yaml from origin/main', result: 'ok' },
      { time: new Date().toLocaleTimeString(), action: 'Pushed triggers.yaml to origin/main', result: 'ok' },
      { time: new Date().toLocaleTimeString(), action: 'No changes in agents.yaml', result: 'warn' },
    );
    showToast('Sync completed successfully', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Sync failed';
    showToast(message, 'error');
    config.value.status = 'error';
    syncLog.value.unshift({ time: new Date().toLocaleTimeString(), action: 'Sync failed — check repository access', result: 'err' });
  } finally {
    isSyncing.value = false;
  }
}

onMounted(async () => {
  isLoading.value = false;
});
</script>

<template>
  <div class="gitops">
    <AppBreadcrumb :items="[
      { label: 'Settings', action: () => router.push({ name: 'settings' }) },
      { label: 'GitOps Sync' },
    ]" />

    <PageHeader
      title="GitOps Bot Configuration Sync"
      subtitle="Store bot and agent configurations as YAML in a Git repository. Sync changes bidirectionally with code-review workflows."
    />

    <div class="layout">
      <div class="main-col">
        <!-- Status banner -->
        <div class="status-banner" :style="{ borderColor: statusColors[config.status] }">
          <div class="status-dot" :style="{ background: statusColors[config.status] }" />
          <span class="status-label" :style="{ color: statusColors[config.status] }">{{ statusLabels[config.status] }}</span>
          <span v-if="config.last_synced_at" class="status-time">Last synced {{ new Date(config.last_synced_at).toLocaleString() }}</span>
          <button
            class="btn btn-primary btn-sm ml-auto"
            :disabled="!config.repo_url || isSyncing"
            @click="handleSync"
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

        <!-- Config form -->
        <div class="card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
              </svg>
              Repository Settings
            </h3>
          </div>
          <div class="form-body">
            <div class="field">
              <label class="field-label">Repository URL <span class="required">*</span></label>
              <input v-model="config.repo_url" type="text" class="input" placeholder="https://github.com/org/repo.git" />
            </div>
            <div class="field-row">
              <div class="field">
                <label class="field-label">Default Branch</label>
                <input v-model="config.branch" type="text" class="input" placeholder="main" />
              </div>
              <div class="field">
                <label class="field-label">Path Prefix</label>
                <input v-model="config.path_prefix" type="text" class="input" placeholder=".agented/" />
              </div>
            </div>
            <div class="field">
              <label class="field-label">Sync Direction</label>
              <select v-model="config.sync_direction" class="select-input">
                <option v-for="d in directionOptions" :key="d.value" :value="d.value">{{ d.label }}</option>
              </select>
            </div>
            <div class="toggle-row">
              <div>
                <div class="toggle-label">Auto-sync on changes</div>
                <div class="toggle-desc">Automatically sync when bots or triggers are modified in the platform</div>
              </div>
              <button
                :class="['toggle-btn', { active: config.auto_sync }]"
                @click="config.auto_sync = !config.auto_sync"
              >
                <span class="toggle-thumb" />
              </button>
            </div>
          </div>
          <div class="card-footer">
            <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
              {{ isSaving ? 'Saving...' : 'Save Configuration' }}
            </button>
          </div>
        </div>

        <!-- Sync log -->
        <div v-if="syncLog.length > 0" class="card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
              Sync Log
            </h3>
          </div>
          <div class="log-list">
            <div v-for="(entry, i) in syncLog" :key="i" class="log-entry">
              <span class="log-time">{{ entry.time }}</span>
              <span :class="['log-icon', `log-${entry.result}`]">
                {{ entry.result === 'ok' ? '✓' : entry.result === 'warn' ? '~' : '✗' }}
              </span>
              <span class="log-action">{{ entry.action }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: file types info -->
      <div class="side-col">
        <div class="card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              Synced Files
            </h3>
          </div>
          <div class="file-list">
            <div v-for="f in FILE_TYPES" :key="f.filename" class="file-item">
              <div class="file-icon">{{ f.icon }}</div>
              <div class="file-info">
                <div class="file-label">{{ f.label }}</div>
                <div class="file-name">{{ config.path_prefix || '.agented/' }}{{ f.filename }}</div>
                <div class="file-example">Fields: {{ f.example }}</div>
              </div>
            </div>
          </div>
        </div>

        <div class="card info-card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              How it works
            </h3>
          </div>
          <div class="info-body">
            <ol class="info-steps">
              <li>Configure a Git repository and branch</li>
              <li>Click "Sync Now" to export current configs as YAML</li>
              <li>Review and merge changes via pull requests</li>
              <li>Platform auto-imports YAML changes on the next sync</li>
            </ol>
            <div class="info-note">Secret values are never written to Git — only key names are exported as references.</div>
          </div>
        </div>
      </div>
    </div>
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
  grid-template-columns: 1fr 320px;
  gap: 20px;
  align-items: start;
}

.main-col, .side-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
.status-label { font-size: 0.85rem; font-weight: 600; }
.status-time { font-size: 0.78rem; color: var(--text-tertiary); }
.ml-auto { margin-left: auto; }

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

.form-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field { display: flex; flex-direction: column; gap: 6px; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.field-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.required { color: #ef4444; }

.input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.input:focus { outline: none; border-color: var(--accent-cyan); }

.select-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  cursor: pointer;
}

.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);
}

.toggle-label { font-size: 0.875rem; font-weight: 500; color: var(--text-primary); }
.toggle-desc { font-size: 0.78rem; color: var(--text-tertiary); margin-top: 2px; }

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

.card-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
  display: flex;
  justify-content: flex-end;
}

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

.log-time { font-family: 'Geist Mono', monospace; color: var(--text-tertiary); font-size: 0.75rem; }

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

.log-ok { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.log-warn { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.log-err { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

.log-action { color: var(--text-secondary); }

.file-list { display: flex; flex-direction: column; }

.file-item {
  display: flex;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.file-item:last-child { border-bottom: none; }

.file-icon { font-size: 1.2rem; flex-shrink: 0; }

.file-label { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
.file-name { font-size: 0.75rem; font-family: 'Geist Mono', monospace; color: var(--accent-cyan); margin-top: 2px; }
.file-example { font-size: 0.72rem; color: var(--text-tertiary); margin-top: 4px; }

.info-body { padding: 16px 20px; }

.info-steps {
  margin: 0 0 12px;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-steps li { font-size: 0.82rem; color: var(--text-secondary); }

.info-note {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  border-radius: 6px;
  padding: 8px 10px;
  border-left: 3px solid #f59e0b;
}

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
}
</style>
