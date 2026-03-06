<script setup lang="ts">
import { ref } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();

type ExportTarget = 'prometheus' | 'datadog' | 'grafana';

interface ExportConfig {
  id: string;
  target: ExportTarget;
  label: string;
  endpoint: string;
  apiKey: string;
  enabled: boolean;
  lastPushed: string | null;
  metrics: string[];
}

const configs = ref<ExportConfig[]>([
  {
    id: 'exp-1',
    target: 'prometheus',
    label: 'Prometheus Scrape',
    endpoint: 'http://prometheus:9090/metrics',
    apiKey: '',
    enabled: true,
    lastPushed: '2 minutes ago',
    metrics: ['execution_count', 'execution_duration_seconds', 'execution_success_rate'],
  },
  {
    id: 'exp-2',
    target: 'datadog',
    label: 'Datadog Events',
    endpoint: 'https://api.datadoghq.com/api/v1/series',
    apiKey: 'dd-key-••••••••',
    enabled: false,
    lastPushed: null,
    metrics: ['bot.execution.count', 'bot.execution.duration', 'bot.token.usage'],
  },
]);

const targetMeta: Record<ExportTarget, { color: string; icon: string }> = {
  prometheus: { color: '#e84118', icon: 'P' },
  datadog: { color: '#7c3aed', icon: 'D' },
  grafana: { color: '#f97316', icon: 'G' },
};

const availableMetrics = [
  'execution_count', 'execution_duration_seconds', 'execution_success_rate',
  'token_usage_total', 'token_cost_usd', 'bot_health_score',
  'trigger_fire_count', 'queue_depth', 'active_bots',
];

const showAddModal = ref(false);
const newTarget = ref<ExportTarget>('prometheus');
const newLabel = ref('');
const newEndpoint = ref('');
const newApiKey = ref('');
const newMetrics = ref<string[]>([...availableMetrics.slice(0, 3)]);

function toggleEnabled(cfg: ExportConfig) {
  cfg.enabled = !cfg.enabled;
  showToast(`${cfg.label} export ${cfg.enabled ? 'enabled' : 'disabled'}`, 'success');
}

function testConnection(cfg: ExportConfig) {
  showToast(`Testing connection to ${cfg.label}...`, 'success');
  setTimeout(() => showToast(`${cfg.label} connection successful`, 'success'), 1200);
}

function removeConfig(id: string) {
  const idx = configs.value.findIndex(c => c.id === id);
  if (idx !== -1) configs.value.splice(idx, 1);
  showToast('Export target removed', 'success');
}

function toggleMetric(m: string) {
  const idx = newMetrics.value.indexOf(m);
  if (idx === -1) newMetrics.value.push(m);
  else newMetrics.value.splice(idx, 1);
}

function saveConfig() {
  if (!newLabel.value.trim() || !newEndpoint.value.trim()) {
    showToast('Label and endpoint are required', 'error');
    return;
  }
  configs.value.push({
    id: `exp-${Date.now()}`,
    target: newTarget.value,
    label: newLabel.value.trim(),
    endpoint: newEndpoint.value.trim(),
    apiKey: newApiKey.value,
    enabled: true,
    lastPushed: null,
    metrics: [...newMetrics.value],
  });
  showAddModal.value = false;
  showToast(`${newLabel.value.trim()} export target added`, 'success');
}
</script>

<template>
  <div class="metrics-export">
    <AppBreadcrumb :items="[{ label: 'Admin' }, { label: 'Metrics Export' }]" />

    <PageHeader
      title="Metrics Export"
      subtitle="Export execution metrics to Prometheus, Grafana, or Datadog for unified observability."
    >
      <template #actions>
        <button class="btn btn-primary" @click="showAddModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Add Target
        </button>
      </template>
    </PageHeader>

    <div class="info-banner">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <span>Prometheus metrics are available at <code>/metrics</code>. Configure Datadog/Grafana push targets to forward metrics automatically.</span>
    </div>

    <div class="configs-grid">
      <div v-for="cfg in configs" :key="cfg.id" class="card config-card">
        <div class="config-card-header">
          <div class="target-badge" :style="{ background: targetMeta[cfg.target].color + '20', color: targetMeta[cfg.target].color }">
            {{ targetMeta[cfg.target].icon }}
          </div>
          <div class="config-title-area">
            <span class="config-label">{{ cfg.label }}</span>
            <span class="config-endpoint">{{ cfg.endpoint }}</span>
          </div>
          <div class="config-status" :class="{ active: cfg.enabled }">
            {{ cfg.enabled ? 'Active' : 'Paused' }}
          </div>
        </div>

        <div class="metrics-section">
          <span class="section-label">Exported metrics</span>
          <div class="metrics-chips">
            <span v-for="m in cfg.metrics" :key="m" class="metric-chip">{{ m }}</span>
          </div>
        </div>

        <div v-if="cfg.lastPushed" class="last-push">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          Last pushed {{ cfg.lastPushed }}
        </div>

        <div class="config-actions">
          <button class="btn btn-sm btn-secondary" @click="testConnection(cfg)">Test</button>
          <button class="btn btn-sm" :class="cfg.enabled ? 'btn-pause' : 'btn-primary'" @click="toggleEnabled(cfg)">
            {{ cfg.enabled ? 'Pause' : 'Enable' }}
          </button>
          <button class="icon-btn" @click="removeConfig(cfg.id)" title="Remove">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Add Modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>Add Export Target</h3>
          <button class="icon-btn" @click="showAddModal = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="field-group">
            <label class="field-label">Target Type</label>
            <select v-model="newTarget" class="select-input">
              <option value="prometheus">Prometheus</option>
              <option value="datadog">Datadog</option>
              <option value="grafana">Grafana</option>
            </select>
          </div>
          <div class="field-group">
            <label class="field-label">Label</label>
            <input v-model="newLabel" type="text" class="text-input" placeholder="e.g. Production Prometheus" />
          </div>
          <div class="field-group">
            <label class="field-label">Endpoint URL</label>
            <input v-model="newEndpoint" type="text" class="text-input" placeholder="https://..." />
          </div>
          <div class="field-group">
            <label class="field-label">API Key (optional)</label>
            <input v-model="newApiKey" type="password" class="text-input" placeholder="Leave blank for unauthenticated" />
          </div>
          <div class="field-group">
            <label class="field-label">Metrics to Export</label>
            <div class="metric-checkboxes">
              <label v-for="m in availableMetrics" :key="m" class="metric-check">
                <input type="checkbox" :checked="newMetrics.includes(m)" @change="toggleMetric(m)" />
                <code>{{ m }}</code>
              </label>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showAddModal = false">Cancel</button>
          <button class="btn btn-primary" @click="saveConfig">Add Target</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.metrics-export {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.info-banner {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 16px;
  background: rgba(6, 182, 212, 0.05);
  border: 1px solid rgba(6, 182, 212, 0.2);
  border-radius: 10px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.info-banner svg { color: var(--accent-cyan); flex-shrink: 0; margin-top: 1px; }

.info-banner code {
  font-family: monospace;
  font-size: 0.8rem;
  background: var(--bg-tertiary);
  padding: 1px 5px;
  border-radius: 3px;
  color: var(--accent-cyan);
}

.configs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
}

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.config-card {
  display: flex;
  flex-direction: column;
}

.config-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px;
  border-bottom: 1px solid var(--border-default);
}

.target-badge {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  font-weight: 700;
  flex-shrink: 0;
}

.config-title-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.config-label {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.config-endpoint {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.config-status {
  font-size: 0.72rem;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-tertiary);
  white-space: nowrap;
}

.config-status.active {
  background: rgba(52, 211, 153, 0.1);
  border-color: rgba(52, 211, 153, 0.3);
  color: #34d399;
}

.metrics-section {
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-label {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.metrics-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.metric-chip {
  font-size: 0.7rem;
  font-family: monospace;
  padding: 2px 7px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-secondary);
}

.last-push {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 18px 10px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.config-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--border-subtle);
  margin-top: auto;
}

.btn {
  display: flex;
  align-items: center;
  gap: 5px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 6px 12px; font-size: 0.8rem; }
.btn:not(.btn-sm) { padding: 8px 16px; font-size: 0.875rem; }

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover { opacity: 0.85; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); }

.btn-pause {
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: #f59e0b;
}

.icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  margin-left: auto;
}

.icon-btn:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  width: 520px;
  max-width: 95vw;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.modal-header h3 { font-size: 1rem; font-weight: 600; color: var(--text-primary); margin: 0; }

.modal-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-default);
}

.field-group { display: flex; flex-direction: column; gap: 6px; }

.field-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.text-input, .select-input {
  padding: 9px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus, .select-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.metric-checkboxes {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.metric-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.metric-check code {
  font-family: monospace;
  font-size: 0.72rem;
  color: var(--text-secondary);
}
</style>
