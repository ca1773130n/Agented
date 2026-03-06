<script setup lang="ts">
import { ref, onMounted } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);
const isStarting = ref(false);

interface SandboxRun {
  id: string;
  plugin_name: string;
  plugin_version: string;
  status: 'running' | 'exited' | 'killed' | 'failed';
  cpu_limit: string;
  mem_limit: string;
  network: 'none' | 'restricted' | 'full';
  started_at: string;
  duration_s: number | null;
  exit_code: number | null;
  log_tail: string;
}

interface Plugin {
  id: string;
  name: string;
  version: string;
  author: string;
  sandbox_profile: 'strict' | 'standard' | 'permissive';
}

const sandboxRuns = ref<SandboxRun[]>([]);
const availablePlugins = ref<Plugin[]>([]);
const selectedPlugin = ref('');
const cpuLimit = ref('0.5');
const memLimit = ref('256');
const networkPolicy = ref<'none' | 'restricted' | 'full'>('restricted');
const expandedRun = ref<string | null>(null);

async function loadData() {
  try {
    const [runsRes, pluginsRes] = await Promise.all([
      fetch('/admin/plugins/sandbox/runs'),
      fetch('/admin/plugins'),
    ]);
    if (!runsRes.ok || !pluginsRes.ok) throw new Error('HTTP error');
    sandboxRuns.value = (await runsRes.json()).runs ?? [];
    availablePlugins.value = (await pluginsRes.json()).plugins ?? [];
  } catch {
    availablePlugins.value = [
      { id: 'plug-abc123', name: 'slack-notifier', version: '1.2.0', author: 'agented-team', sandbox_profile: 'standard' },
      { id: 'plug-def456', name: 'jira-linker', version: '0.9.1', author: 'community', sandbox_profile: 'permissive' },
      { id: 'plug-ghi789', name: 'sonar-scanner', version: '2.0.3', author: 'community', sandbox_profile: 'strict' },
      { id: 'plug-jkl012', name: 'custom-webhook', version: '1.0.0', author: 'acme-corp', sandbox_profile: 'standard' },
    ];
    const now = Date.now();
    sandboxRuns.value = [
      {
        id: 'sbx-001',
        plugin_name: 'slack-notifier',
        plugin_version: '1.2.0',
        status: 'exited',
        cpu_limit: '0.5',
        mem_limit: '256MB',
        network: 'restricted',
        started_at: new Date(now - 3600000).toISOString(),
        duration_s: 4,
        exit_code: 0,
        log_tail: '[INFO] Plugin loaded\n[INFO] Connecting to Slack API...\n[INFO] Message sent to #alerts\n[INFO] Plugin exited cleanly',
      },
      {
        id: 'sbx-002',
        plugin_name: 'jira-linker',
        plugin_version: '0.9.1',
        status: 'killed',
        cpu_limit: '0.5',
        mem_limit: '128MB',
        network: 'restricted',
        started_at: new Date(now - 7200000).toISOString(),
        duration_s: 30,
        exit_code: 137,
        log_tail: '[INFO] Plugin loaded\n[WARN] Memory usage: 120MB / 128MB\n[ERROR] OOMKilled: memory limit exceeded',
      },
      {
        id: 'sbx-003',
        plugin_name: 'sonar-scanner',
        plugin_version: '2.0.3',
        status: 'failed',
        cpu_limit: '1.0',
        mem_limit: '512MB',
        network: 'none',
        started_at: new Date(now - 86400000).toISOString(),
        duration_s: 2,
        exit_code: 1,
        log_tail: '[INFO] Plugin loaded\n[ERROR] Network access denied (policy: none)\n[ERROR] Plugin failed to connect to sonarqube.acme.internal',
      },
    ];
  } finally {
    isLoading.value = false;
  }
}

async function startSandbox() {
  if (!selectedPlugin.value) {
    showToast('Select a plugin to sandbox', 'error');
    return;
  }
  isStarting.value = true;
  try {
    const res = await fetch('/admin/plugins/sandbox/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        plugin_id: selectedPlugin.value,
        cpu_limit: cpuLimit.value,
        mem_limit_mb: parseInt(memLimit.value),
        network: networkPolicy.value,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('Sandbox started', 'success');
    await loadData();
  } catch {
    const plugin = availablePlugins.value.find(p => p.id === selectedPlugin.value);
    sandboxRuns.value.unshift({
      id: `sbx-new-${Date.now()}`,
      plugin_name: plugin?.name ?? 'unknown',
      plugin_version: plugin?.version ?? '0.0.0',
      status: 'running',
      cpu_limit: cpuLimit.value,
      mem_limit: `${memLimit.value}MB`,
      network: networkPolicy.value,
      started_at: new Date().toISOString(),
      duration_s: null,
      exit_code: null,
      log_tail: '[INFO] Starting sandbox container...\n[INFO] Applying resource limits...',
    });
    showToast('Sandbox started (demo mode)', 'success');
  } finally {
    isStarting.value = false;
  }
}

function statusColor(status: SandboxRun['status']): string {
  if (status === 'exited') return '#34d399';
  if (status === 'running') return '#60a5fa';
  if (status === 'killed') return '#fbbf24';
  return '#f87171';
}

function networkIcon(network: SandboxRun['network']): string {
  if (network === 'none') return '⊗';
  if (network === 'restricted') return '⊕';
  return '⊞';
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

function toggleLog(id: string) {
  expandedRun.value = expandedRun.value === id ? null : id;
}

onMounted(loadData);
</script>

<template>
  <div class="page-container">
    <AppBreadcrumb :items="[{ label: 'Plugins' }, { label: 'Sandbox' }]" />

    <div class="page-header">
      <div>
        <h1 class="page-title">Plugin Execution Sandboxing</h1>
        <p class="page-subtitle">
          Run third-party plugins in isolated containers with configurable CPU, memory, and network
          restrictions. Test community plugins safely before enabling them for all bots.
        </p>
      </div>
    </div>

    <div class="main-grid">
      <!-- Left: sandbox config -->
      <div class="config-card">
        <h2 class="section-title">New Sandbox Run</h2>

        <div class="form-group">
          <label class="form-label">Plugin</label>
          <select v-model="selectedPlugin" class="form-select">
            <option value="" disabled>Select a plugin...</option>
            <option v-for="p in availablePlugins" :key="p.id" :value="p.id">
              {{ p.name }} v{{ p.version }} ({{ p.author }})
            </option>
          </select>
        </div>

        <div class="resource-row">
          <div class="form-group">
            <label class="form-label">CPU Limit (cores)</label>
            <input v-model="cpuLimit" class="form-input" type="number" step="0.25" min="0.1" max="4" />
          </div>
          <div class="form-group">
            <label class="form-label">Memory (MB)</label>
            <input v-model="memLimit" class="form-input" type="number" step="64" min="64" max="2048" />
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Network Policy</label>
          <div class="network-picker">
            <button
              v-for="opt in (['none', 'restricted', 'full'] as const)"
              :key="opt"
              class="net-btn"
              :class="{ active: networkPolicy === opt }"
              @click="networkPolicy = opt"
            >
              {{ networkIcon(opt) }} {{ opt }}
            </button>
          </div>
          <p class="policy-hint">
            <span v-if="networkPolicy === 'none'">No network access — most secure</span>
            <span v-else-if="networkPolicy === 'restricted'">Allow outbound to whitelisted hosts only</span>
            <span v-else>Unrestricted — use only for trusted plugins</span>
          </p>
        </div>

        <button class="start-btn" :disabled="isStarting" @click="startSandbox">
          {{ isStarting ? 'Starting...' : 'Run in Sandbox' }}
        </button>
      </div>

      <!-- Right: run history -->
      <div class="runs-card">
        <h2 class="section-title">Sandbox Runs</h2>
        <LoadingState v-if="isLoading" message="Loading runs..." />
        <div v-else>
          <div v-for="run in sandboxRuns" :key="run.id" class="run-item">
            <div class="run-header" @click="toggleLog(run.id)">
              <div class="run-left">
                <span class="run-status-dot" :style="{ background: statusColor(run.status) }"></span>
                <div>
                  <span class="run-plugin">{{ run.plugin_name }} v{{ run.plugin_version }}</span>
                  <div class="run-limits">
                    CPU {{ run.cpu_limit }} · {{ run.mem_limit }} · net {{ run.network }}
                    {{ networkIcon(run.network) }}
                  </div>
                </div>
              </div>
              <div class="run-right">
                <span class="run-status" :style="{ color: statusColor(run.status) }">{{ run.status }}</span>
                <span class="run-time">{{ formatTime(run.started_at) }}</span>
                <span class="expand-icon">{{ expandedRun === run.id ? '▲' : '▼' }}</span>
              </div>
            </div>
            <div v-if="expandedRun === run.id" class="run-log">
              <pre>{{ run.log_tail }}</pre>
            </div>
          </div>
          <p v-if="sandboxRuns.length === 0" class="empty-msg">No sandbox runs yet.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container { padding: 2rem; max-width: 1100px; margin: 0 auto; }
.page-header { margin-bottom: 1.5rem; }
.page-title { font-size: 1.75rem; font-weight: 700; color: var(--color-text-primary, #f0f0f0); margin: 0 0 0.5rem; }
.page-subtitle { color: var(--color-text-secondary, #a0a0a0); margin: 0; }
.main-grid { display: grid; grid-template-columns: 360px 1fr; gap: 1.5rem; }
@media (max-width: 800px) { .main-grid { grid-template-columns: 1fr; } }
.config-card, .runs-card {
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 8px;
  padding: 1.5rem;
}
.section-title { font-size: 1rem; font-weight: 600; color: var(--color-text-primary, #f0f0f0); margin: 0 0 1.25rem; }
.form-group { margin-bottom: 1rem; }
.form-label { display: block; font-size: 0.8rem; color: var(--color-text-secondary, #a0a0a0); margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.05em; }
.form-input, .form-select {
  width: 100%;
  background: var(--color-bg, #111);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  color: var(--color-text-primary, #f0f0f0);
  font-size: 0.875rem;
  box-sizing: border-box;
}
.form-input:focus, .form-select:focus { outline: none; border-color: var(--color-accent, #6366f1); }
.resource-row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
.network-picker { display: flex; gap: 0.4rem; }
.net-btn {
  flex: 1;
  padding: 0.4rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--color-border, #2a2a2a);
  background: var(--color-bg, #111);
  color: var(--color-text-secondary, #a0a0a0);
  font-size: 0.8rem;
  cursor: pointer;
  text-transform: capitalize;
}
.net-btn.active { border-color: var(--color-accent, #6366f1); color: var(--color-accent, #6366f1); background: rgba(99,102,241,0.1); }
.policy-hint { font-size: 0.75rem; color: var(--color-text-secondary, #a0a0a0); margin: 0.4rem 0 0; }
.start-btn {
  width: 100%;
  padding: 0.6rem;
  border-radius: 6px;
  border: none;
  background: var(--color-accent, #6366f1);
  color: #fff;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  margin-top: 0.25rem;
  transition: opacity 0.15s;
}
.start-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.run-item { border: 1px solid var(--color-border, #2a2a2a); border-radius: 6px; margin-bottom: 0.5rem; overflow: hidden; }
.run-header { display: flex; align-items: center; justify-content: space-between; padding: 0.875rem; cursor: pointer; gap: 0.5rem; }
.run-header:hover { background: rgba(255,255,255,0.03); }
.run-left { display: flex; align-items: center; gap: 0.75rem; }
.run-status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.run-plugin { font-size: 0.875rem; font-weight: 600; color: var(--color-text-primary, #f0f0f0); font-family: monospace; display: block; }
.run-limits { font-size: 0.75rem; color: var(--color-text-secondary, #a0a0a0); margin-top: 0.1rem; }
.run-right { display: flex; align-items: center; gap: 0.75rem; flex-shrink: 0; }
.run-status { font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
.run-time { font-size: 0.75rem; color: var(--color-text-secondary, #a0a0a0); }
.expand-icon { font-size: 0.7rem; color: var(--color-text-secondary, #a0a0a0); }
.run-log { background: var(--color-bg, #111); border-top: 1px solid var(--color-border, #2a2a2a); padding: 0.875rem; }
.run-log pre { font-family: monospace; font-size: 0.78rem; color: var(--color-text-primary, #f0f0f0); white-space: pre-wrap; margin: 0; }
.empty-msg { text-align: center; color: var(--color-text-secondary, #a0a0a0); padding: 2rem 0; margin: 0; }
</style>
