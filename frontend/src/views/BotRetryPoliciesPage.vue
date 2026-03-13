<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import { triggerApi, ApiError } from '../services/api';
import type { Trigger } from '../services/api';

const router = useRouter();
const showToast = useToast();

const isLoading = ref(true);
const error = ref('');

type BackoffStrategy = 'linear' | 'exponential' | 'fixed';
type RetryCondition = 'rate_limit' | 'error' | 'timeout' | 'any';

interface RetryPolicy {
  id: string;
  botId: string;
  botName: string;
  enabled: boolean;
  maxAttempts: number;
  backoffStrategy: BackoffStrategy;
  initialDelayMs: number;
  maxDelayMs: number;
  retryOn: RetryCondition[];
  successCount: number;
  failCount: number;
  timeoutSeconds: number | null;
}

const policies = ref<RetryPolicy[]>([]);

const editingId = ref<string | null>(null);
const savingId = ref<string | null>(null);
const showNewForm = ref(false);

const newPolicy = ref<Omit<RetryPolicy, 'id' | 'successCount' | 'failCount' | 'timeoutSeconds'>>({
  botId: '',
  botName: '',
  enabled: true,
  maxAttempts: 3,
  backoffStrategy: 'exponential',
  initialDelayMs: 2000,
  maxDelayMs: 60000,
  retryOn: ['rate_limit', 'timeout'],
});

function triggerToPolicy(t: Trigger): RetryPolicy {
  const timeout = t.timeout_seconds ?? 300;
  return {
    id: t.id,
    botId: t.id,
    botName: t.name,
    enabled: !!t.enabled,
    maxAttempts: 3,
    backoffStrategy: 'exponential',
    initialDelayMs: Math.min(timeout * 100, 5000),
    maxDelayMs: Math.min(timeout * 1000, 60000),
    retryOn: ['rate_limit', 'timeout'],
    successCount: 0,
    failCount: 0,
    timeoutSeconds: timeout,
  };
}

async function loadPolicies() {
  isLoading.value = true;
  error.value = '';
  try {
    const resp = await triggerApi.list();
    const triggers = resp.triggers ?? [];
    policies.value = triggers.map(triggerToPolicy);
  } catch (e) {
    if (e instanceof ApiError) {
      error.value = e.message;
    } else {
      error.value = 'Failed to load retry policies';
    }
    showToast(error.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

function strategyLabel(s: BackoffStrategy): string {
  return { linear: 'Linear', exponential: 'Exponential', fixed: 'Fixed' }[s];
}

function conditionLabel(c: RetryCondition): string {
  return { rate_limit: 'Rate limit', error: 'Error', timeout: 'Timeout', any: 'Any failure' }[c];
}

function successRate(p: RetryPolicy): number {
  const total = p.successCount + p.failCount;
  return total === 0 ? 100 : Math.round((p.successCount / total) * 100);
}

async function togglePolicy(p: RetryPolicy) {
  const prev = p.enabled;
  p.enabled = !p.enabled;
  try {
    await triggerApi.update(p.botId, { enabled: p.enabled ? 1 : 0 });
    showToast(`Policy ${p.enabled ? 'enabled' : 'disabled'}`, 'success');
  } catch {
    p.enabled = prev;
    showToast('Failed to update policy', 'error');
  }
}

async function savePolicy(p: RetryPolicy) {
  savingId.value = p.id;
  try {
    await triggerApi.update(p.botId, {
      timeout_seconds: Math.round(p.maxDelayMs / 1000),
    });
    editingId.value = null;
    showToast('Retry policy saved', 'success');
  } catch {
    showToast('Failed to save policy', 'error');
  } finally {
    savingId.value = null;
  }
}

async function addPolicy() {
  if (!newPolicy.value.botName.trim()) {
    showToast('Bot name is required', 'info');
    return;
  }
  try {
    await triggerApi.create({
      name: newPolicy.value.botName,
      prompt_template: 'Retry policy placeholder',
      timeout_seconds: Math.round(newPolicy.value.maxDelayMs / 1000),
    });
    showNewForm.value = false;
    newPolicy.value = {
      botId: '',
      botName: '',
      enabled: true,
      maxAttempts: 3,
      backoffStrategy: 'exponential',
      initialDelayMs: 2000,
      maxDelayMs: 60000,
      retryOn: ['rate_limit', 'timeout'],
    };
    showToast('Policy created', 'success');
    await loadPolicies();
  } catch {
    showToast('Failed to create policy', 'error');
  }
}

function toggleCondition(p: RetryPolicy | typeof newPolicy.value, c: RetryCondition) {
  const list = 'retryOn' in p ? p.retryOn : (p as typeof newPolicy.value).retryOn;
  const idx = list.indexOf(c);
  if (idx >= 0) list.splice(idx, 1);
  else list.push(c);
}

onMounted(loadPolicies);
</script>

<template>
  <div class="retry-policies-page">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Retry Policies' },
    ]" />

    <PageHeader
      title="Smart Retry Policies"
      subtitle="Configure per-bot retry behavior: max attempts, backoff strategy, and retry conditions."
    />

    <LoadingState v-if="isLoading" message="Loading retry policies..." />

    <div v-else-if="error" class="card error-card">
      <p class="error-text">{{ error }}</p>
      <button class="btn btn-primary" @click="loadPolicies">Retry</button>
    </div>

    <template v-else>
      <!-- Summary stats -->
      <div class="stat-row">
        <div class="stat-card">
          <span class="stat-val">{{ policies.filter(p => p.enabled).length }}</span>
          <span class="stat-label">Active policies</span>
        </div>
        <div class="stat-card">
          <span class="stat-val">{{ policies.reduce((s, p) => s + p.maxAttempts, 0) }}</span>
          <span class="stat-label">Max total attempts</span>
        </div>
        <div class="stat-card">
          <span class="stat-val">{{ policies.length > 0 ? Math.round(policies.reduce((s, p) => s + successRate(p), 0) / policies.length) : 0 }}%</span>
          <span class="stat-label">Avg success rate</span>
        </div>
      </div>

      <!-- Policies list -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <polyline points="1 4 1 10 7 10"/>
              <path d="M3.51 15a9 9 0 1 0 .49-3.75"/>
            </svg>
            Bot Retry Policies
          </h3>
          <button class="btn btn-primary" @click="showNewForm = !showNewForm">+ Add Policy</button>
        </div>

        <!-- New policy form -->
        <div v-if="showNewForm" class="new-policy-form">
          <div class="form-grid">
            <div class="form-field">
              <label>Bot Name</label>
              <input v-model="newPolicy.botName" type="text" class="text-input" placeholder="e.g. Dependency Updater" />
            </div>
            <div class="form-field">
              <label>Max Attempts</label>
              <input v-model.number="newPolicy.maxAttempts" type="number" min="1" max="10" class="text-input" />
            </div>
            <div class="form-field">
              <label>Backoff Strategy</label>
              <select v-model="newPolicy.backoffStrategy" class="select-input">
                <option value="fixed">Fixed</option>
                <option value="linear">Linear</option>
                <option value="exponential">Exponential</option>
              </select>
            </div>
            <div class="form-field">
              <label>Initial Delay (ms)</label>
              <input v-model.number="newPolicy.initialDelayMs" type="number" min="500" step="500" class="text-input" />
            </div>
            <div class="form-field">
              <label>Max Delay (ms)</label>
              <input v-model.number="newPolicy.maxDelayMs" type="number" min="1000" step="1000" class="text-input" />
            </div>
          </div>
          <div class="form-field">
            <label>Retry On</label>
            <div class="condition-chips">
              <button
                v-for="c in (['rate_limit', 'error', 'timeout', 'any'] as RetryCondition[])"
                :key="c"
                class="chip"
                :class="{ active: newPolicy.retryOn.includes(c) }"
                @click="toggleCondition(newPolicy, c)"
              >
                {{ conditionLabel(c) }}
              </button>
            </div>
          </div>
          <div class="form-actions">
            <button class="btn btn-ghost" @click="showNewForm = false">Cancel</button>
            <button class="btn btn-primary" @click="addPolicy">Create Policy</button>
          </div>
        </div>

        <!-- Existing policies -->
        <div class="policies-list">
          <div v-for="p in policies" :key="p.id" class="policy-row">
            <div class="policy-main">
              <div class="policy-identity">
                <span class="bot-name">{{ p.botName }}</span>
                <span class="bot-id">{{ p.botId }}</span>
              </div>
              <div class="policy-stats">
                <span class="stat-chip">{{ p.maxAttempts }}x max</span>
                <span class="stat-chip strategy">{{ strategyLabel(p.backoffStrategy) }}</span>
                <span class="stat-chip delay">{{ (p.initialDelayMs / 1000).toFixed(1) }}s → {{ (p.maxDelayMs / 1000).toFixed(0) }}s</span>
              </div>
              <div class="condition-tags">
                <span v-for="c in p.retryOn" :key="c" class="cond-tag">{{ conditionLabel(c) }}</span>
              </div>
              <div class="success-bar-wrap">
                <div class="success-bar-track">
                  <div
                    class="success-bar-fill"
                    :style="{ width: successRate(p) + '%' }"
                  />
                </div>
                <span class="success-pct">{{ successRate(p) }}% success ({{ p.successCount + p.failCount }} runs)</span>
              </div>
            </div>
            <div class="policy-controls">
              <label class="toggle">
                <input type="checkbox" :checked="p.enabled" @change="togglePolicy(p)" />
                <span class="toggle-track" />
              </label>
              <button class="btn-icon" :title="editingId === p.id ? 'Cancel' : 'Edit'" @click="editingId = editingId === p.id ? null : p.id">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
            </div>

            <!-- Inline edit panel -->
            <div v-if="editingId === p.id" class="edit-panel">
              <div class="form-grid">
                <div class="form-field">
                  <label>Max Attempts</label>
                  <input v-model.number="p.maxAttempts" type="number" min="1" max="10" class="text-input" />
                </div>
                <div class="form-field">
                  <label>Backoff Strategy</label>
                  <select v-model="p.backoffStrategy" class="select-input">
                    <option value="fixed">Fixed</option>
                    <option value="linear">Linear</option>
                    <option value="exponential">Exponential</option>
                  </select>
                </div>
                <div class="form-field">
                  <label>Initial Delay (ms)</label>
                  <input v-model.number="p.initialDelayMs" type="number" min="500" step="500" class="text-input" />
                </div>
                <div class="form-field">
                  <label>Max Delay (ms)</label>
                  <input v-model.number="p.maxDelayMs" type="number" min="1000" step="1000" class="text-input" />
                </div>
              </div>
              <div class="form-field">
                <label>Retry On</label>
                <div class="condition-chips">
                  <button
                    v-for="c in (['rate_limit', 'error', 'timeout', 'any'] as RetryCondition[])"
                    :key="c"
                    class="chip"
                    :class="{ active: p.retryOn.includes(c) }"
                    @click="toggleCondition(p, c)"
                  >
                    {{ conditionLabel(c) }}
                  </button>
                </div>
              </div>
              <div class="form-actions">
                <button class="btn btn-ghost" @click="editingId = null">Cancel</button>
                <button class="btn btn-primary" :disabled="savingId === p.id" @click="savePolicy(p)">
                  {{ savingId === p.id ? 'Saving...' : 'Save' }}
                </button>
              </div>
            </div>
          </div>
          <div v-if="policies.length === 0" class="list-empty">No retry policies configured</div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.retry-policies-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.error-card {
  padding: 32px 24px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.error-text {
  font-size: 0.875rem;
  color: #ef4444;
  margin: 0;
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

.stat-val {
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--accent-cyan);
}

.stat-label {
  font-size: 0.8rem;
  color: var(--text-tertiary);
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

.new-policy-form {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
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
}

.text-input:focus,
.select-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.condition-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  padding: 4px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 20px;
  font-size: 0.78rem;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.chip.active {
  background: rgba(6, 182, 212, 0.15);
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.form-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.policies-list {
  display: flex;
  flex-direction: column;
}

.policy-row {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.policy-row:last-child { border-bottom: none; }

.policy-main {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.policy-identity {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.bot-name {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.bot-id {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-family: monospace;
}

.policy-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.stat-chip {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.stat-chip.strategy { color: var(--accent-cyan); background: rgba(6, 182, 212, 0.1); }
.stat-chip.delay { color: var(--accent-amber, #f59e0b); background: rgba(245, 158, 11, 0.1); }

.condition-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.cond-tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  background: rgba(139, 92, 246, 0.1);
  border: 1px solid rgba(139, 92, 246, 0.25);
  border-radius: 4px;
  color: #a78bfa;
}

.success-bar-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.success-bar-track {
  flex: 1;
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}

.success-bar-fill {
  height: 100%;
  background: var(--accent-emerald, #34d399);
  border-radius: 2px;
  transition: width 0.4s ease;
}

.success-pct {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.policy-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  position: absolute;
  right: 24px;
  top: 16px;
}

.policy-row { position: relative; }

.toggle {
  position: relative;
  width: 36px;
  height: 20px;
  cursor: pointer;
}

.toggle input { opacity: 0; width: 0; height: 0; }

.toggle-track {
  position: absolute;
  inset: 0;
  background: var(--bg-tertiary);
  border-radius: 10px;
  border: 1px solid var(--border-default);
  transition: all 0.2s;
}

.toggle input:checked + .toggle-track {
  background: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.toggle-track::after {
  content: '';
  position: absolute;
  width: 14px;
  height: 14px;
  top: 2px;
  left: 2px;
  background: white;
  border-radius: 50%;
  transition: left 0.2s;
}

.toggle input:checked + .toggle-track::after { left: 18px; }

.btn-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.btn-icon:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.edit-panel {
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  border: 1px solid var(--border-default);
}

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
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost { background: transparent; border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--text-secondary); color: var(--text-primary); }
</style>
