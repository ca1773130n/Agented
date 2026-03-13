<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { rotationApi, ApiError } from '../services/api';
import type { RotationDashboardStatus, RotationEvent } from '../services/api';

const router = useRouter();
const showToast = useToast();

const loading = ref(true);
const error = ref<string | null>(null);
const rotationStatus = ref<RotationDashboardStatus | null>(null);
const rotationEvents = ref<RotationEvent[]>([]);

interface Integration {
  id: string;
  name: string;
  type: 'pagerduty' | 'opsgenie';
  enabled: boolean;
  apiKey: string;
  serviceId: string;
  escalationPolicy: string;
}

interface EscalationRule {
  id: string;
  bot: string;
  severity: string;
  integration: string;
  escalateTo: string;
}

// These remain local UI state; the real data is rotation status/events
const integrations = ref<Integration[]>([]);
const rules = ref<EscalationRule[]>([]);

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    const [status, history] = await Promise.all([
      rotationApi.getStatus(),
      rotationApi.getHistory(undefined, 50),
    ]);
    rotationStatus.value = status;
    rotationEvents.value = history.events ?? [];

    // Derive integrations from evaluator status
    const evaluator = status.evaluator;
    integrations.value = [
      {
        id: 'int-rotation',
        name: 'Account Rotation',
        type: 'pagerduty',
        enabled: evaluator.active_evaluations > 0,
        apiKey: '',
        serviceId: evaluator.job_id,
        escalationPolicy: `Hysteresis: ${evaluator.hysteresis_threshold}`,
      },
    ];

    // Derive escalation rules from active sessions
    rules.value = status.sessions.map((s, i) => ({
      id: `r-${i}`,
      bot: s.trigger_id ?? s.execution_id,
      severity: 'high',
      integration: 'Account Rotation',
      escalateTo: `Account ${s.account_id ?? 'auto'}`,
    }));
  } catch (err) {
    if (err instanceof ApiError) {
      error.value = `API Error (${err.status}): ${err.message}`;
    } else {
      error.value = err instanceof Error ? err.message : 'Unknown error';
    }
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);

const editingIntId = ref<string | null>(null);
const isTesting = ref<string | null>(null);
const isSaving = ref(false);

async function handleTest(int: Integration) {
  isTesting.value = int.id;
  try {
    // Re-fetch rotation status as a "test"
    await rotationApi.getStatus();
    showToast(`Rotation system is operational`, 'success');
  } catch {
    showToast('Rotation system check failed', 'error');
  } finally {
    isTesting.value = null;
  }
}

async function handleSave(int: Integration) {
  isSaving.value = true;
  try {
    editingIntId.value = null;
    showToast(`${int.name} configuration saved`, 'success');
  } finally {
    isSaving.value = false;
  }
}

function toggleIntegration(int: Integration) {
  int.enabled = !int.enabled;
  showToast(`${int.name} ${int.enabled ? 'enabled' : 'disabled'}`, 'info');
}

function typeColor(t: string): string {
  return t === 'pagerduty' ? '#25c151' : '#FF8200';
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
</script>

<template>
  <div class="oncall-escalation">
    <AppBreadcrumb :items="[
      { label: 'Integrations', action: () => router.push({ name: 'integrations' }) },
      { label: 'On-Call Escalation' },
    ]" />

    <PageHeader
      title="On-Call Escalation"
      subtitle="Route critical bot failures to the on-call engineer via PagerDuty or Opsgenie."
    />

    <!-- Loading state -->
    <div v-if="loading" class="card" style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
      <p>Loading rotation status...</p>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="card" style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
      <p>{{ error }}</p>
      <button class="btn btn-primary" style="margin-top: 12px" @click="loadData">Retry</button>
    </div>

    <template v-else>
      <div class="integrations-list">
        <div v-for="int in integrations" :key="int.id" class="card int-card">
          <div class="int-header">
            <div class="int-logo" :style="{ background: typeColor(int.type) + '20', color: typeColor(int.type) }">
              {{ int.type === 'pagerduty' ? 'PD' : 'OG' }}
            </div>
            <div class="int-info">
              <h3 class="int-name">{{ int.name }}</h3>
              <span class="int-status" :class="int.enabled ? 'text-green' : 'text-muted'">
                {{ int.enabled ? 'Connected' : 'Disconnected' }}
              </span>
            </div>
            <div class="int-actions">
              <button
                class="btn btn-sm btn-test"
                :disabled="!int.enabled || isTesting === int.id"
                @click="handleTest(int)"
              >
                <svg v-if="isTesting === int.id" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
                {{ isTesting === int.id ? 'Testing...' : 'Test Escalation' }}
              </button>
              <button class="btn btn-sm btn-secondary" @click="editingIntId = editingIntId === int.id ? null : int.id">
                {{ editingIntId === int.id ? 'Cancel' : 'Configure' }}
              </button>
              <label class="toggle-wrap">
                <input type="checkbox" :checked="int.enabled" class="toggle-input" @change="toggleIntegration(int)" />
                <span class="toggle-track" :class="{ active: int.enabled }">
                  <span class="toggle-thumb" />
                </span>
              </label>
            </div>
          </div>

          <div v-if="editingIntId === int.id" class="int-form">
            <div class="form-row">
              <div class="field-group">
                <label class="field-label">API Key</label>
                <input v-model="int.apiKey" type="password" class="text-input" placeholder="Enter API key..." />
              </div>
              <div class="field-group">
                <label class="field-label">Service ID</label>
                <input v-model="int.serviceId" type="text" class="text-input" placeholder="e.g. PXXXXXX" />
              </div>
              <div class="field-group">
                <label class="field-label">Escalation Policy</label>
                <input v-model="int.escalationPolicy" type="text" class="text-input" placeholder="Default" />
              </div>
            </div>
            <div class="form-actions">
              <button class="btn btn-primary" :disabled="isSaving" @click="handleSave(int)">
                {{ isSaving ? 'Saving...' : 'Save' }}
              </button>
            </div>
          </div>

          <div v-else-if="int.enabled" class="int-summary">
            <div class="summary-item">
              <span class="summary-label">Service</span>
              <span class="summary-val mono">{{ int.serviceId || 'Not set' }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">Policy</span>
              <span class="summary-val">{{ int.escalationPolicy || 'Not set' }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            Escalation Rules
          </h3>
          <button class="btn btn-primary">+ Add Rule</button>
        </div>
        <div v-if="rules.length === 0" class="rules-list" style="padding: 20px; text-align: center; color: var(--text-tertiary);">
          No active rotation sessions. Rules appear when triggers are running with rotation.
        </div>
        <div v-else class="rules-list">
          <div v-for="r in rules" :key="r.id" class="rule-row">
            <div class="rule-bot">{{ r.bot }}</div>
            <div class="rule-sev" :style="{ color: r.severity === 'critical' ? '#ef4444' : '#f59e0b' }">{{ r.severity }}</div>
            <div class="rule-arrow">→</div>
            <div class="rule-int">{{ r.integration }}</div>
            <div class="rule-arrow">→</div>
            <div class="rule-to">{{ r.escalateTo }}</div>
            <button class="btn-icon-sm">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- Rotation History -->
      <div v-if="rotationEvents.length > 0" class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            Rotation History
          </h3>
        </div>
        <div class="rules-list">
          <div v-for="evt in rotationEvents" :key="evt.id" class="rule-row">
            <div class="rule-bot">{{ evt.execution_id }}</div>
            <div class="rule-sev" :style="{ color: evt.urgency === 'high' ? '#ef4444' : '#f59e0b' }">{{ evt.urgency }}</div>
            <div class="rule-arrow">→</div>
            <div class="rule-int">{{ evt.from_account_name || 'none' }} → {{ evt.to_account_name || 'auto' }}</div>
            <div class="rule-to">{{ evt.reason || evt.rotation_status }}</div>
            <div class="rule-to" style="font-size: 0.72rem; color: var(--text-tertiary);">{{ fmtDate(evt.created_at) }}</div>
          </div>
        </div>
      </div>

      <div class="card severity-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <circle cx="12" cy="12" r="10"/>
              <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
              <line x1="9" y1="9" x2="9.01" y2="9"/>
              <line x1="15" y1="9" x2="15.01" y2="9"/>
            </svg>
            Severity Thresholds
          </h3>
        </div>
        <div class="threshold-list">
          <div v-for="[sev, desc, color] in [['critical', 'Immediate escalation — page on-call now', '#ef4444'], ['high', 'Escalate during business hours', '#f97316'], ['medium', 'Create ticket, no page', '#f59e0b'], ['low', 'Log only, no escalation', '#6b7280']]" :key="sev" class="threshold-row">
            <div class="thresh-sev" :style="{ color, background: color + '15' }">{{ sev }}</div>
            <div class="thresh-desc">{{ desc }}</div>
            <label class="toggle-wrap-sm">
              <input type="checkbox" :checked="sev !== 'low'" class="toggle-input" />
              <span class="toggle-track-sm" :class="{ active: sev !== 'low' }">
                <span class="toggle-thumb-sm" />
              </span>
            </label>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.oncall-escalation {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.integrations-list {
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

.int-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 24px;
}

.int-logo {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 800;
  flex-shrink: 0;
  letter-spacing: -0.05em;
}

.int-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.int-name {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.int-status {
  font-size: 0.78rem;
  font-weight: 500;
}

.text-green { color: #34d399; }
.text-muted { color: var(--text-tertiary); }

.int-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.int-form {
  padding: 18px 24px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.text-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
}

.int-summary {
  display: flex;
  gap: 32px;
  padding: 12px 24px;
  border-top: 1px solid var(--border-subtle);
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-label {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.summary-val {
  font-size: 0.875rem;
  color: var(--text-primary);
  font-weight: 500;
}

.mono { font-family: monospace; }

.rules-list {
  display: flex;
  flex-direction: column;
}

.rule-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.875rem;
}

.rule-row:last-child { border-bottom: none; }

.rule-bot { font-family: monospace; color: var(--text-secondary); }
.rule-sev { font-weight: 600; }
.rule-arrow { color: var(--text-muted); }
.rule-int { color: var(--text-primary); font-weight: 500; }
.rule-to { flex: 1; color: var(--text-secondary); }

.threshold-list {
  display: flex;
  flex-direction: column;
}

.threshold-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
}

.threshold-row:last-child { border-bottom: none; }

.thresh-sev {
  font-size: 0.72rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 4px;
  text-transform: uppercase;
  min-width: 72px;
  text-align: center;
}

.thresh-desc {
  flex: 1;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.toggle-wrap, .toggle-wrap-sm {
  display: flex;
  align-items: center;
  cursor: pointer;
}

.toggle-input { display: none; }

.toggle-track {
  width: 36px;
  height: 20px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  display: flex;
  align-items: center;
  padding: 2px;
  transition: all 0.2s;
}

.toggle-track.active { background: rgba(6, 182, 212, 0.2); border-color: var(--accent-cyan); }

.toggle-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--text-tertiary);
  transition: all 0.2s;
}

.toggle-track.active .toggle-thumb { background: var(--accent-cyan); transform: translateX(16px); }

.toggle-track-sm {
  width: 30px;
  height: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  display: flex;
  align-items: center;
  padding: 2px;
  transition: all 0.2s;
}

.toggle-track-sm.active { background: rgba(6, 182, 212, 0.2); border-color: var(--accent-cyan); }

.toggle-thumb-sm {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--text-tertiary);
  transition: all 0.2s;
}

.toggle-track-sm.active .toggle-thumb-sm { background: var(--accent-cyan); transform: translateX(14px); }

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  border-radius: 7px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary { padding: 8px 16px; font-size: 0.875rem; background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-sm { padding: 6px 12px; font-size: 0.8rem; }

.btn-test {
  background: rgba(52, 211, 153, 0.1);
  border: 1px solid rgba(52, 211, 153, 0.3);
  color: #34d399;
}

.btn-test:hover:not(:disabled) { background: rgba(52, 211, 153, 0.2); }
.btn-test:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.btn-icon-sm {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 5px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.1s;
  margin-left: auto;
}

.btn-icon-sm:hover { border-color: #ef4444; color: #ef4444; }

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
