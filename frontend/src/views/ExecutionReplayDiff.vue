<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import type { Execution, ReplayComparison, OutputDiff } from '../services/api';
import { executionApi, replayApi, ApiError } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const executions = ref<Execution[]>([]);
const selectedExecA = ref('');
const selectedExecB = ref('');
const comparison = ref<ReplayComparison | null>(null);
const diff = ref<OutputDiff | null>(null);
const isLoading = ref(true);
const isReplaying = ref(false);
const isLoadingDiff = ref(false);

const filteredExecsB = computed(() =>
  executions.value.filter(e => e.execution_id !== selectedExecA.value)
);

async function loadExecutions() {
  try {
    const res = await executionApi.listAll({ limit: 50 });
    executions.value = res.executions ?? [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load executions';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function handleReplay() {
  if (!selectedExecA.value) return;
  isReplaying.value = true;
  try {
    await replayApi.create(selectedExecA.value, 'Manual replay from diff viewer');
    showToast('Replay started successfully', 'success');
    await loadExecutions();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to start replay';
    showToast(message, 'error');
  } finally {
    isReplaying.value = false;
  }
}

async function handleLoadDiff() {
  if (!selectedExecA.value) return;
  isLoadingDiff.value = true;
  try {
    const comparisons = await replayApi.getComparisons(selectedExecA.value);
    const list = comparisons.comparisons ?? [];
    if (list.length === 0) {
      showToast('No comparisons found for this execution', 'info');
      return;
    }
    comparison.value = list[0];
    const diffData = await replayApi.getDiff(list[0].id);
    diff.value = diffData;
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load diff';
    showToast(message, 'error');
  } finally {
    isLoadingDiff.value = false;
  }
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function statusClass(status: string): string {
  const map: Record<string, string> = { success: 'status-success', failed: 'status-failed', running: 'status-running' };
  return map[status] ?? 'status-idle';
}

onMounted(loadExecutions);
</script>

<template>
  <div class="replay-diff">

    <PageHeader
      title="Execution Replay & Diff"
      subtitle="Compare two execution outputs side-by-side and replay past executions."
    />

    <LoadingState v-if="isLoading" message="Loading executions..." />

    <template v-else>
      <div class="card selector-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/>
              <polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>
            </svg>
            Select Executions to Compare
          </h3>
        </div>
        <div class="selector-body">
          <div class="selector-row">
            <div class="selector-group">
              <label class="field-label">Execution A (base)</label>
              <select v-model="selectedExecA" class="select-input">
                <option value="">-- Select execution --</option>
                <option v-for="ex in executions" :key="ex.execution_id" :value="ex.execution_id">
                  {{ ex.execution_id.slice(0, 8) }} — {{ ex.status }} — {{ formatDate(ex.started_at) }}
                </option>
              </select>
            </div>
            <div class="selector-vs">vs</div>
            <div class="selector-group">
              <label class="field-label">Execution B (compare)</label>
              <select v-model="selectedExecB" class="select-input">
                <option value="">-- Select execution --</option>
                <option v-for="ex in filteredExecsB" :key="ex.execution_id" :value="ex.execution_id">
                  {{ ex.execution_id.slice(0, 8) }} — {{ ex.status }} — {{ formatDate(ex.started_at) }}
                </option>
              </select>
            </div>
          </div>
          <div class="selector-actions">
            <button
              class="btn btn-secondary"
              :disabled="!selectedExecA || isLoadingDiff"
              @click="handleLoadDiff"
            >
              <svg v-if="isLoadingDiff" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
              </svg>
              {{ isLoadingDiff ? 'Loading...' : 'Load Diff' }}
            </button>
            <button
              class="btn btn-primary"
              :disabled="!selectedExecA || isReplaying"
              @click="handleReplay"
            >
              <svg v-if="isReplaying" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              {{ isReplaying ? 'Replaying...' : 'Replay Execution A' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Executions list -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="9" y1="9" x2="15" y2="9"/>
              <line x1="9" y1="15" x2="15" y2="15"/>
            </svg>
            Recent Executions
          </h3>
          <span class="card-badge">{{ executions.length }} total</span>
        </div>
        <div class="exec-list">
          <div
            v-for="ex in executions.slice(0, 20)"
            :key="ex.execution_id"
            class="exec-row"
            :class="{ selected: ex.execution_id === selectedExecA || ex.execution_id === selectedExecB }"
            @click="selectedExecA ? (selectedExecB = ex.execution_id) : (selectedExecA = ex.execution_id)"
          >
            <span class="exec-id">{{ ex.execution_id.slice(0, 12) }}</span>
            <span :class="['exec-status', statusClass(ex.status)]">{{ ex.status }}</span>
            <span class="exec-date">{{ formatDate(ex.started_at) }}</span>
            <span v-if="ex.execution_id === selectedExecA" class="exec-tag tag-a">A</span>
            <span v-else-if="ex.execution_id === selectedExecB" class="exec-tag tag-b">B</span>
          </div>
        </div>
      </div>

      <!-- Diff view -->
      <div v-if="diff" class="card diff-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <line x1="5" y1="12" x2="19" y2="12"/>
              <polyline points="12 5 19 12 12 19"/>
            </svg>
            Output Diff
          </h3>
          <span class="badge-info">{{ comparison ? 'compared' : 'comparing' }}</span>
        </div>
        <div class="diff-body">
          <div class="diff-panels">
            <div class="diff-panel">
              <div class="diff-panel-label">Original</div>
              <pre class="diff-pre">{{ diff.diff_lines.filter(l => l.type !== 'added').map(l => l.content).join('\n') || '(no output)' }}</pre>
            </div>
            <div class="diff-panel">
              <div class="diff-panel-label">Replay</div>
              <pre class="diff-pre">{{ diff.diff_lines.filter(l => l.type !== 'removed').map(l => l.content).join('\n') || '(no output)' }}</pre>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.replay-diff {
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

.card-header h3 svg {
  color: var(--accent-cyan);
}

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

.badge-info {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 3px 10px;
  background: rgba(99, 102, 241, 0.15);
  color: #818cf8;
  border-radius: 4px;
  text-transform: uppercase;
}

.selector-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.selector-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 16px;
  align-items: end;
}

.selector-vs {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  font-weight: 600;
  padding-bottom: 10px;
  text-align: center;
}

.selector-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 0.8rem;
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
  cursor: pointer;
}

.select-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.selector-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--text-primary); }
.btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }

.exec-list {
  display: flex;
  flex-direction: column;
}

.exec-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background 0.1s;
}

.exec-row:hover { background: var(--bg-tertiary); }
.exec-row.selected { background: rgba(6, 182, 212, 0.06); }
.exec-row:last-child { border-bottom: none; }

.exec-id {
  font-family: monospace;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.exec-status {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.status-success { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.status-failed { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.status-running { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
.status-idle { background: rgba(156, 163, 175, 0.1); color: #6b7280; }

.exec-date {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  margin-left: auto;
}

.exec-tag {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
}

.tag-a { background: rgba(6, 182, 212, 0.2); color: var(--accent-cyan); }
.tag-b { background: rgba(139, 92, 246, 0.2); color: #a78bfa; }

.diff-body { padding: 24px; }

.diff-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.diff-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.diff-panel-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.diff-pre {
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
  word-break: break-all;
}

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .selector-row { grid-template-columns: 1fr; }
  .selector-vs { display: none; }
  .diff-panels { grid-template-columns: 1fr; }
}
</style>
