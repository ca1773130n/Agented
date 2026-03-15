<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { executionApi, triggerApi, ApiError } from '../services/api';
import type { Execution, Trigger } from '../services/api';

const router = useRouter();
const showToast = useToast();

interface WebhookRecord {
  id: string;
  source: string;
  bot: string;
  receivedAt: string;
  method: string;
  path: string;
  payload: Record<string, unknown>;
  statusCode: number;
}

const loading = ref(true);
const error = ref('');
const records = ref<WebhookRecord[]>([]);
const triggers = ref<Trigger[]>([]);

function executionToRecord(exec: Execution): WebhookRecord {
  return {
    id: exec.execution_id,
    source: exec.trigger_type || 'webhook',
    bot: exec.trigger_id || exec.trigger_name || '',
    receivedAt: exec.started_at,
    method: 'POST',
    path: exec.trigger_type === 'webhook' ? '/api/webhooks/github' : `/admin/triggers/${exec.trigger_id}/run`,
    payload: {
      execution_id: exec.execution_id,
      trigger_name: exec.trigger_name,
      status: exec.status,
      prompt: exec.prompt || '',
      backend_type: exec.backend_type,
      ...(exec.error_message ? { error: exec.error_message } : {}),
    },
    statusCode: exec.status === 'success' ? 200 : exec.status === 'failed' ? 500 : 202,
  };
}

async function fetchData() {
  loading.value = true;
  error.value = '';
  try {
    const [execResult, triggerResult] = await Promise.all([
      executionApi.listAll({ limit: 50 }),
      triggerApi.list(),
    ]);
    records.value = (execResult?.executions || []).map(executionToRecord);
    triggers.value = triggerResult?.triggers || [];
  } catch (err) {
    if (err instanceof ApiError) {
      error.value = `Failed to load webhook records: ${err.message}`;
    } else {
      error.value = 'Failed to load webhook records';
    }
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);

const filterSource = ref('');
const filterBot = ref('');
const filterDate = ref('');
const selectedRecord = ref<WebhookRecord | null>(null);
const isReplaying = ref<string | null>(null);

const sources = computed(() => [...new Set(records.value.map(r => r.source))]);
const bots = computed(() => [...new Set(records.value.map(r => r.bot))]);

const filtered = computed(() => records.value.filter(r => {
  if (filterSource.value && r.source !== filterSource.value) return false;
  if (filterBot.value && r.bot !== filterBot.value) return false;
  if (filterDate.value) {
    const d = new Date(r.receivedAt).toISOString().slice(0, 10);
    if (d !== filterDate.value) return false;
  }
  return true;
}));

async function handleReplay(r: WebhookRecord) {
  isReplaying.value = r.id;
  try {
    // Find the trigger to re-run it
    const trigger = triggers.value.find(t => t.id === r.bot);
    if (trigger) {
      await triggerApi.run(trigger.id);
      showToast(`Webhook ${r.id} replayed successfully`, 'success');
    } else {
      showToast('Cannot replay: trigger not found', 'error');
    }
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : 'Replay failed', 'error');
  } finally {
    isReplaying.value = null;
  }
}

function formatDate(ts: string): string {
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function statusClass(code: number): string {
  if (code >= 200 && code < 300) return 'status-ok';
  if (code >= 400) return 'status-error';
  return 'status-warn';
}
</script>

<template>
  <div class="webhook-recorder">

    <PageHeader
      title="Webhook Recorder"
      subtitle="Browse, inspect, and replay captured webhook payloads."
    />

    <!-- Loading state -->
    <div v-if="loading" class="card" style="padding: 48px; text-align: center;">
      <div style="color: var(--text-tertiary); font-size: 0.875rem;">Loading webhook records...</div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="card" style="padding: 48px; text-align: center;">
      <div style="color: #ef4444; font-size: 0.875rem; margin-bottom: 12px;">{{ error }}</div>
      <button class="btn btn-ghost" @click="fetchData">Retry</button>
    </div>

    <div v-else class="main-layout">
      <div class="left-panel">
        <div class="filters card">
          <div class="filter-header">Filters</div>
          <div class="filter-body">
            <div class="field-group">
              <label class="field-label">Source</label>
              <select v-model="filterSource" class="select-input">
                <option value="">All sources</option>
                <option v-for="s in sources" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <div class="field-group">
              <label class="field-label">Bot</label>
              <select v-model="filterBot" class="select-input">
                <option value="">All bots</option>
                <option v-for="b in bots" :key="b" :value="b">{{ b }}</option>
              </select>
            </div>
            <div class="field-group">
              <label class="field-label">Date</label>
              <input v-model="filterDate" type="date" class="select-input" />
            </div>
            <button class="btn btn-ghost" @click="filterSource = ''; filterBot = ''; filterDate = ''">
              Clear filters
            </button>
          </div>
        </div>

        <div class="card records-card">
          <div class="records-header">
            <span class="records-count">{{ filtered.length }} webhook{{ filtered.length !== 1 ? 's' : '' }}</span>
          </div>
          <div class="records-list">
            <div
              v-for="r in filtered"
              :key="r.id"
              class="record-row"
              :class="{ active: selectedRecord?.id === r.id }"
              @click="selectedRecord = r"
            >
              <div class="record-top">
                <span class="record-source">{{ r.source }}</span>
                <span :class="['record-status', statusClass(r.statusCode)]">{{ r.statusCode }}</span>
              </div>
              <div class="record-bot">{{ r.bot }}</div>
              <div class="record-date">{{ formatDate(r.receivedAt) }}</div>
            </div>
            <div v-if="filtered.length === 0" class="records-empty">
              No webhooks match filters
            </div>
          </div>
        </div>
      </div>

      <div class="right-panel">
        <div v-if="!selectedRecord" class="card empty-detail">
          <div class="empty-inner">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="40" height="40" style="color: var(--text-tertiary); opacity: 0.4">
              <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 11 19.79 19.79 0 0 1 1.61 2.18 2 2 0 0 1 3.6.01h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 7.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/>
            </svg>
            <p>Select a webhook to inspect its payload</p>
          </div>
        </div>

        <div v-else class="card detail-card">
          <div class="detail-header">
            <div>
              <div class="detail-title">{{ selectedRecord.source }} webhook</div>
              <div class="detail-sub">{{ selectedRecord.path }} · {{ formatDate(selectedRecord.receivedAt) }}</div>
            </div>
            <div class="detail-actions">
              <button
                class="btn btn-primary"
                :disabled="isReplaying === selectedRecord.id"
                @click="handleReplay(selectedRecord)"
              >
                <svg v-if="isReplaying === selectedRecord.id" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <polygon points="5 3 19 12 5 21 5 3"/>
                </svg>
                {{ isReplaying === selectedRecord.id ? 'Replaying...' : 'Replay' }}
              </button>
            </div>
          </div>
          <div class="detail-meta-row">
            <span class="meta-chip">Method: {{ selectedRecord.method }}</span>
            <span :class="['meta-chip', statusClass(selectedRecord.statusCode)]">Status: {{ selectedRecord.statusCode }}</span>
            <span class="meta-chip">Bot: {{ selectedRecord.bot }}</span>
          </div>
          <div class="payload-section">
            <div class="payload-label">Payload</div>
            <pre class="payload-pre">{{ JSON.stringify(selectedRecord.payload, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.webhook-recorder {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.main-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 20px;
  align-items: start;
}

.left-panel {
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

.filters {
  padding: 0;
}

.filter-header {
  padding: 14px 18px;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-default);
}

.filter-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-weight: 500;
}

.select-input {
  padding: 7px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.8rem;
  cursor: pointer;
}

.select-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.records-card { }

.records-header {
  padding: 12px 18px;
  border-bottom: 1px solid var(--border-default);
}

.records-count {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  font-weight: 500;
}

.records-list {
  display: flex;
  flex-direction: column;
}

.record-row {
  padding: 12px 18px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background 0.1s;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.record-row:hover { background: var(--bg-tertiary); }
.record-row.active { background: rgba(6, 182, 212, 0.08); border-left: 2px solid var(--accent-cyan); }
.record-row:last-child { border-bottom: none; }

.record-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.record-source {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: capitalize;
}

.record-status {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
}

.status-ok { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.status-error { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.status-warn { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }

.record-bot {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-family: monospace;
}

.record-date {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.records-empty {
  padding: 24px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

.right-panel {}

.empty-detail {
  padding: 64px 24px;
}

.empty-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.empty-inner p {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin: 0;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.detail-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
  text-transform: capitalize;
}

.detail-sub {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  font-family: monospace;
}

.detail-actions {
  display: flex;
  gap: 10px;
}

.detail-meta-row {
  display: flex;
  gap: 10px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
  flex-wrap: wrap;
}

.meta-chip {
  font-size: 0.75rem;
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-secondary);
}

.payload-section {
  padding: 20px 24px;
}

.payload-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 10px;
}

.payload-pre {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 16px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--text-secondary);
  overflow: auto;
  max-height: 400px;
  white-space: pre-wrap;
  margin: 0;
}

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

.btn-ghost {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 4px 0;
}

.btn-ghost:hover { color: var(--accent-cyan); }

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .main-layout { grid-template-columns: 1fr; }
}
</style>
