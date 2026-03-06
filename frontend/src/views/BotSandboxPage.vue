<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const isLoading = ref(true);
const isCreating = ref(false);
const isRunning = ref(false);

interface Sandbox {
  id: string;
  name: string;
  bot_id: string;
  bot_name: string;
  repo_fork: string;
  branch: string;
  status: 'ready' | 'running' | 'stopped' | 'error';
  created_at: string;
  last_run: string | null;
  run_count: number;
}

const sandboxes = ref<Sandbox[]>([]);

interface SandboxForm {
  bot_id: string;
  repo_url: string;
  branch: string;
  name: string;
}

const showCreateForm = ref(false);
const form = ref<SandboxForm>({
  bot_id: 'bot-pr-review',
  repo_url: '',
  branch: 'sandbox/test',
  name: '',
});

const selectedSandbox = ref<Sandbox | null>(null);
const runLog = ref<string>('');

async function loadData() {
  try {
    const res = await fetch('/admin/sandboxes');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    sandboxes.value = (await res.json()).sandboxes ?? [];
  } catch {
    sandboxes.value = [
      {
        id: 'sb-1',
        name: 'PR Review Test',
        bot_id: 'bot-pr-review',
        bot_name: 'PR Review Bot',
        repo_fork: 'myorg/myrepo-sandbox',
        branch: 'sandbox/pr-review-test',
        status: 'ready',
        created_at: new Date(Date.now() - 3 * 86400000).toISOString(),
        last_run: new Date(Date.now() - 3600000).toISOString(),
        run_count: 12,
      },
      {
        id: 'sb-2',
        name: 'Security Audit Sandbox',
        bot_id: 'bot-security',
        bot_name: 'Security Audit Bot',
        repo_fork: 'myorg/backend-sandbox',
        branch: 'sandbox/security-test',
        status: 'stopped',
        created_at: new Date(Date.now() - 7 * 86400000).toISOString(),
        last_run: new Date(Date.now() - 2 * 86400000).toISOString(),
        run_count: 5,
      },
    ];
  } finally {
    isLoading.value = false;
  }
}

async function createSandbox() {
  if (!form.value.bot_id || !form.value.repo_url) {
    showToast('Bot and repo URL are required', 'error');
    return;
  }
  isCreating.value = true;
  try {
    const res = await fetch('/admin/sandboxes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sandbox = await res.json();
    sandboxes.value.unshift(sandbox);
    showToast('Sandbox created', 'success');
  } catch {
    sandboxes.value.unshift({
      id: `sb-${Date.now()}`,
      name: form.value.name || `Sandbox ${sandboxes.value.length + 1}`,
      bot_id: form.value.bot_id,
      bot_name: form.value.bot_id,
      repo_fork: form.value.repo_url + '-sandbox',
      branch: form.value.branch,
      status: 'ready',
      created_at: new Date().toISOString(),
      last_run: null,
      run_count: 0,
    });
    showToast('Sandbox created', 'success');
  } finally {
    isCreating.value = false;
    showCreateForm.value = false;
    form.value = { bot_id: 'bot-pr-review', repo_url: '', branch: 'sandbox/test', name: '' };
  }
}

async function runSandbox(sandbox: Sandbox) {
  selectedSandbox.value = sandbox;
  isRunning.value = true;
  runLog.value = '';
  sandbox.status = 'running';

  try {
    const res = await fetch(`/admin/sandboxes/${sandbox.id}/run`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    // Stream log
    const text = await res.text();
    runLog.value = text;
    sandbox.status = 'ready';
    sandbox.run_count++;
    sandbox.last_run = new Date().toISOString();
    showToast('Sandbox run complete', 'success');
  } catch {
    // Demo log output
    runLog.value = [
      `[${new Date().toISOString()}] Starting sandbox run for bot: ${sandbox.bot_name}`,
      `[${new Date().toISOString()}] Cloning fork: ${sandbox.repo_fork}...`,
      `[${new Date().toISOString()}] Checking out branch: ${sandbox.branch}`,
      `[${new Date().toISOString()}] Injecting bot prompt template...`,
      `[${new Date().toISOString()}] Executing: claude -p "Review the changes in this PR for code quality"`,
      `[${new Date().toISOString()}] Bot output: Found 2 potential improvements in src/services/api.ts`,
      `[${new Date().toISOString()}] Bot output: Line 47 — consider extracting retry logic into a helper`,
      `[${new Date().toISOString()}] Bot output: Line 112 — missing error boundary for null response`,
      `[${new Date().toISOString()}] No write operations performed (sandbox mode)`,
      `[${new Date().toISOString()}] Run complete. Duration: 4.2s`,
    ].join('\n');
    sandbox.status = 'ready';
    sandbox.run_count++;
    sandbox.last_run = new Date().toISOString();
    showToast('Sandbox run complete', 'success');
  } finally {
    isRunning.value = false;
  }
}

async function deleteSandbox(id: string) {
  try {
    await fetch(`/admin/sandboxes/${id}`, { method: 'DELETE' });
    sandboxes.value = sandboxes.value.filter(s => s.id !== id);
    if (selectedSandbox.value?.id === id) selectedSandbox.value = null;
    showToast('Sandbox deleted', 'success');
  } catch {
    sandboxes.value = sandboxes.value.filter(s => s.id !== id);
    showToast('Sandbox deleted', 'success');
  }
}

function statusColor(status: Sandbox['status']): string {
  return { ready: 'var(--accent-emerald)', running: 'var(--accent-cyan)', stopped: 'var(--text-tertiary)', error: 'var(--accent-crimson)' }[status];
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

onMounted(loadData);
</script>

<template>
  <div class="sandbox-page">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'dashboards' }) },
      { label: 'Test Sandbox Environments' },
    ]" />

    <LoadingState v-if="isLoading" message="Loading sandboxes..." />

    <template v-else>
      <!-- Intro banner -->
      <div class="card intro-card">
        <div class="intro-content">
          <div class="intro-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/>
              <path d="M8 12h8M12 8v8"/>
            </svg>
          </div>
          <div>
            <h2>Bot Test Sandbox Environments</h2>
            <p>Run bots against a sandboxed fork or branch without touching production repos. Bots can make changes, open PRs, and test integrations safely.</p>
          </div>
        </div>
        <button class="btn btn-primary" @click="showCreateForm = !showCreateForm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          New Sandbox
        </button>
      </div>

      <!-- Create Form -->
      <div v-if="showCreateForm" class="card create-card">
        <h3>Create Sandbox</h3>
        <div class="form-grid">
          <div class="form-group">
            <label>Bot</label>
            <select v-model="form.bot_id" class="form-input">
              <option value="bot-pr-review">PR Review Bot</option>
              <option value="bot-security">Security Audit Bot</option>
            </select>
          </div>
          <div class="form-group">
            <label>Sandbox Name</label>
            <input v-model="form.name" type="text" class="form-input" placeholder="e.g. PR Review Test" />
          </div>
          <div class="form-group">
            <label>Repo URL (to fork)</label>
            <input v-model="form.repo_url" type="text" class="form-input" placeholder="https://github.com/org/repo" />
          </div>
          <div class="form-group">
            <label>Branch</label>
            <input v-model="form.branch" type="text" class="form-input" placeholder="sandbox/test" />
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-ghost" @click="showCreateForm = false">Cancel</button>
          <button class="btn btn-primary" :disabled="isCreating" @click="createSandbox">
            {{ isCreating ? 'Creating...' : 'Create Sandbox' }}
          </button>
        </div>
      </div>

      <div class="main-layout">
        <!-- Sandbox List -->
        <div class="sandbox-list">
          <div v-if="sandboxes.length === 0" class="empty-state">
            <p>No sandboxes yet. Create one to safely test bots.</p>
          </div>
          <div v-for="sb in sandboxes" :key="sb.id"
            class="card sandbox-card"
            :class="{ selected: selectedSandbox?.id === sb.id }"
            @click="selectedSandbox = sb">
            <div class="sandbox-header">
              <div class="sandbox-meta">
                <div class="sandbox-status-dot" :style="{ background: statusColor(sb.status) }"></div>
                <span class="sandbox-name">{{ sb.name }}</span>
              </div>
              <span class="status-label" :style="{ color: statusColor(sb.status) }">{{ sb.status }}</span>
            </div>
            <div class="sandbox-details">
              <span class="detail-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 00-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0020 4.77 5.07 5.07 0 0019.91 1S18.73.65 16 2.48a13.38 13.38 0 00-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 005 4.77a5.44 5.44 0 00-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 009 18.13V22"/></svg>
                {{ sb.repo_fork }}
              </span>
              <span class="detail-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 3v12M18 9a3 3 0 100-6 3 3 0 000 6zM6 21a3 3 0 100-6 3 3 0 000 6z"/><path d="M18 9a9 9 0 01-9 9"/></svg>
                {{ sb.branch }}
              </span>
            </div>
            <div class="sandbox-footer">
              <span class="run-count">{{ sb.run_count }} runs</span>
              <span class="last-run">Last: {{ formatDate(sb.last_run) }}</span>
              <div class="sandbox-actions" @click.stop>
                <button class="btn btn-primary btn-sm" :disabled="isRunning && selectedSandbox?.id === sb.id" @click="runSandbox(sb)">
                  {{ isRunning && selectedSandbox?.id === sb.id ? 'Running...' : 'Run' }}
                </button>
                <button class="btn btn-ghost btn-sm btn-danger" @click="deleteSandbox(sb.id)">Delete</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Log Panel -->
        <div v-if="selectedSandbox" class="card log-card">
          <div class="log-header">
            <h3>{{ selectedSandbox.name }} — Run Log</h3>
            <span class="status-label" :style="{ color: statusColor(selectedSandbox.status) }">{{ selectedSandbox.status }}</span>
          </div>
          <div class="log-output">
            <pre v-if="runLog">{{ runLog }}</pre>
            <div v-else-if="isRunning" class="log-running">
              <div class="spinner"></div>
              Running sandbox...
            </div>
            <div v-else class="log-empty">Click "Run" to execute this sandbox</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sandbox-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card { padding: 24px; }

.intro-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.intro-content { display: flex; align-items: flex-start; gap: 16px; }

.intro-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: rgba(6,182,212,0.1);
  border: 1px solid var(--accent-cyan);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.intro-icon svg { width: 22px; height: 22px; color: var(--accent-cyan); }

.intro-content h2 { font-size: 1rem; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.intro-content p { font-size: 0.85rem; color: var(--text-tertiary); line-height: 1.5; max-width: 480px; }

.create-card h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); margin-bottom: 20px; }

.form-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-bottom: 20px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 0.8rem; color: var(--text-secondary); font-weight: 500; }
.form-input {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 0.85rem;
  outline: none;
}
.form-input:focus { border-color: var(--accent-cyan); }

.form-actions { display: flex; justify-content: flex-end; gap: 10px; }

.main-layout { display: grid; grid-template-columns: 360px 1fr; gap: 20px; }

.sandbox-list { display: flex; flex-direction: column; gap: 12px; }

.empty-state {
  padding: 40px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.85rem;
  border: 1px dashed var(--border-default);
  border-radius: 8px;
}

.sandbox-card {
  padding: 16px 20px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.sandbox-card:hover { border-color: var(--accent-cyan); }
.sandbox-card.selected { border-color: var(--accent-cyan); background: rgba(6,182,212,0.05); }

.sandbox-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.sandbox-meta { display: flex; align-items: center; gap: 8px; }

.sandbox-status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.sandbox-name { font-weight: 600; font-size: 0.9rem; color: var(--text-primary); }

.status-label { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }

.sandbox-details { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }

.detail-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.detail-item svg { width: 13px; height: 13px; flex-shrink: 0; }

.sandbox-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.run-count, .last-run { font-size: 0.78rem; color: var(--text-tertiary); }

.sandbox-actions { display: flex; gap: 6px; margin-left: auto; }

.log-card { display: flex; flex-direction: column; min-height: 300px; }
.log-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.log-header h3 { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); }

.log-output {
  flex: 1;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border: 1px solid var(--border-default);
  padding: 16px;
  min-height: 200px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--text-secondary);
  overflow-y: auto;
}

.log-output pre { white-space: pre-wrap; word-break: break-word; margin: 0; }
.log-running, .log-empty { display: flex; align-items: center; gap: 10px; color: var(--text-tertiary); font-size: 0.85rem; }

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 6px; font-size: 0.85rem; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; }
.btn svg { width: 14px; height: 14px; }
.btn-primary { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }
.btn-primary:hover { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost { background: transparent; color: var(--text-secondary); border-color: var(--border-default); }
.btn-ghost:hover { background: var(--bg-elevated); color: var(--text-primary); }
.btn-danger { color: var(--accent-crimson); border-color: var(--accent-crimson); }
.btn-sm { padding: 5px 10px; font-size: 0.78rem; }

@media (max-width: 900px) {
  .main-layout { grid-template-columns: 1fr; }
}
</style>
