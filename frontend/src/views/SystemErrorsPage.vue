<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { useSystemErrors } from '../composables/useSystemErrors';
import type { SystemError } from '../services/api/types/system';

const showToast = useToast();

const {
  errors,
  totalCount,
  selectedError,
  isLoading,
  loadError,
  statusFilter,
  categoryFilter,
  sourceFilter,
  searchQuery,
  timeRange,
  loadErrors,
  selectError,
  clearSelection,
  updateStatus,
  retryFix,
  startPolling,
  stopPolling,
} = useSystemErrors();

const stackTraceExpanded = ref(false);
const contextExpanded = ref(false);

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

function truncate(str: string, len: number): string {
  return str.length > len ? str.slice(0, len) + '...' : str;
}

async function onSelectRow(err: SystemError) {
  stackTraceExpanded.value = false;
  contextExpanded.value = false;
  await selectError(err.id);
}

async function onUpdateStatus(status: 'new' | 'investigating' | 'fixed' | 'ignored') {
  if (!selectedError.value) return;
  try {
    await updateStatus(selectedError.value.id, status);
    showToast(`Status updated to ${status}`, 'success');
  } catch {
    showToast('Failed to update status', 'error');
  }
}

async function onRetryFix() {
  if (!selectedError.value) return;
  try {
    await retryFix(selectedError.value.id);
    showToast('Fix retry initiated', 'success');
  } catch {
    showToast('Failed to retry fix', 'error');
  }
}

function applyFilters() {
  loadErrors();
}

onMounted(() => {
  loadErrors();
  startPolling();
});

onUnmounted(() => {
  stopPolling();
});
</script>

<template>
  <div class="system-errors-page">
    <PageHeader title="System Errors" subtitle="Monitor and manage system errors with automated fix tracking" />

    <!-- Filters -->
    <div class="filters-bar">
      <div class="filter-group">
        <label>Status</label>
        <select v-model="statusFilter" @change="applyFilters">
          <option value="">All</option>
          <option value="new">New</option>
          <option value="investigating">Investigating</option>
          <option value="fixed">Fixed</option>
          <option value="ignored">Ignored</option>
        </select>
      </div>
      <div class="filter-group">
        <label>Category</label>
        <select v-model="categoryFilter" @change="applyFilters">
          <option value="">All</option>
          <option value="cli_error">CLI Error</option>
          <option value="proxy_error">Proxy Error</option>
          <option value="streaming_error">Streaming Error</option>
          <option value="runtime_error">Runtime Error</option>
          <option value="frontend_error">Frontend Error</option>
          <option value="db_error">DB Error</option>
        </select>
      </div>
      <div class="filter-group">
        <label>Source</label>
        <select v-model="sourceFilter" @change="applyFilters">
          <option value="">All</option>
          <option value="backend">Backend</option>
          <option value="frontend">Frontend</option>
        </select>
      </div>
      <div class="filter-group">
        <label>Time</label>
        <select v-model="timeRange" @change="applyFilters">
          <option value="hour">Last Hour</option>
          <option value="day">Last 24h</option>
          <option value="week">Last Week</option>
          <option value="all">All Time</option>
        </select>
      </div>
      <div class="filter-group search-group">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search errors..."
          class="search-input"
          @keyup.enter="applyFilters"
        />
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading && !errors.length" class="state-container">
      <div class="spinner"></div>
      <p class="state-message">Loading errors...</p>
    </div>

    <!-- Error State -->
    <div v-else-if="loadError" class="state-container state-error">
      <p class="state-title">Failed to load errors</p>
      <p class="state-message">{{ loadError }}</p>
      <div class="state-action">
        <button class="btn-retry" @click="loadErrors">Retry</button>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else-if="!errors.length && !isLoading" class="state-container state-empty">
      <div class="empty-icon-wrap">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48">
          <path d="M9 12l2 2 4-4"/>
          <circle cx="12" cy="12" r="10"/>
        </svg>
      </div>
      <p class="state-title">No errors found</p>
      <p class="state-message">No system errors match your current filters.</p>
    </div>

    <!-- Content: table + detail -->
    <div v-else class="errors-content" :class="{ 'with-detail': selectedError }">
      <div class="errors-table-wrap">
        <div class="table-header-info">
          <span class="total-count">{{ totalCount }} error{{ totalCount !== 1 ? 's' : '' }}</span>
        </div>
        <table class="errors-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Source</th>
              <th>Category</th>
              <th>Message</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="err in errors"
              :key="err.id"
              :class="{ selected: selectedError?.id === err.id }"
              @click="onSelectRow(err)"
            >
              <td class="col-time">{{ relativeTime(err.timestamp) }}</td>
              <td>
                <span class="source-badge" :class="err.source">{{ err.source }}</span>
              </td>
              <td>
                <span class="category-badge">{{ err.category.replace('_', ' ') }}</span>
              </td>
              <td class="col-message">{{ truncate(err.message, 80) }}</td>
              <td>
                <span class="status-badge" :class="err.status">{{ err.status }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Detail Panel -->
      <div v-if="selectedError" class="detail-panel">
        <div class="detail-header">
          <h3>Error Detail</h3>
          <button class="btn btn-sm" @click="clearSelection">Close</button>
        </div>

        <div class="detail-body">
          <div class="detail-section">
            <div class="detail-row">
              <span class="detail-label">ID</span>
              <span class="detail-value text-mono">{{ selectedError.id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Timestamp</span>
              <span class="detail-value">{{ new Date(selectedError.timestamp).toLocaleString() }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Source</span>
              <span class="source-badge" :class="selectedError.source">{{ selectedError.source }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Category</span>
              <span class="category-badge">{{ selectedError.category }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Status</span>
              <span class="status-badge" :class="selectedError.status">{{ selectedError.status }}</span>
            </div>
            <div v-if="selectedError.request_id" class="detail-row">
              <span class="detail-label">Request ID</span>
              <span class="detail-value text-mono">{{ selectedError.request_id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Hash</span>
              <span class="detail-value text-mono">{{ selectedError.error_hash }}</span>
            </div>
          </div>

          <div class="detail-section">
            <h4>Message</h4>
            <pre class="error-message-block">{{ selectedError.message }}</pre>
          </div>

          <div v-if="selectedError.stack_trace" class="detail-section">
            <button class="collapse-toggle-btn" @click="stackTraceExpanded = !stackTraceExpanded">
              <svg :class="{ rotated: stackTraceExpanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <polyline points="9,18 15,12 9,6"/>
              </svg>
              Stack Trace
            </button>
            <pre v-show="stackTraceExpanded" class="stack-trace-block">{{ selectedError.stack_trace }}</pre>
          </div>

          <div v-if="selectedError.context_json" class="detail-section">
            <button class="collapse-toggle-btn" @click="contextExpanded = !contextExpanded">
              <svg :class="{ rotated: contextExpanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <polyline points="9,18 15,12 9,6"/>
              </svg>
              Context
            </button>
            <pre v-show="contextExpanded" class="context-block">{{ selectedError.context_json }}</pre>
          </div>

          <!-- Fix attempts -->
          <div v-if="selectedError.fix_attempts?.length" class="detail-section">
            <h4>Fix Attempts</h4>
            <div class="fix-attempts-list">
              <div v-for="fix in selectedError.fix_attempts" :key="fix.id" class="fix-attempt-item">
                <div class="fix-row">
                  <span class="fix-tier">Tier {{ fix.tier }}</span>
                  <span class="fix-status-badge" :class="fix.status">{{ fix.status }}</span>
                </div>
                <div v-if="fix.action_taken" class="fix-action">{{ fix.action_taken }}</div>
                <div class="fix-time">{{ relativeTime(fix.started_at) }}</div>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="detail-actions">
            <button
              v-if="selectedError.status === 'new'"
              class="btn btn-sm"
              @click="onUpdateStatus('investigating')"
            >
              Investigate
            </button>
            <button
              v-if="selectedError.status !== 'fixed'"
              class="btn btn-sm btn-primary"
              @click="onRetryFix()"
            >
              Retry Fix
            </button>
            <button
              v-if="selectedError.status !== 'ignored'"
              class="btn btn-sm"
              @click="onUpdateStatus('ignored')"
            >
              Ignore
            </button>
            <button
              v-if="selectedError.status !== 'fixed'"
              class="btn btn-sm"
              style="background: var(--accent-emerald-dim); color: var(--accent-emerald);"
              @click="onUpdateStatus('fixed')"
            >
              Mark Fixed
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.system-errors-page {
  max-width: 1400px;
}

.search-group {
  flex: 1;
  min-width: 200px;
}

.search-input {
  width: 100%;
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
}

.search-input:focus {
  border-color: var(--accent-cyan);
  outline: none;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: global-spin 1s linear infinite;
  margin-bottom: 16px;
}

.empty-icon-wrap {
  color: var(--text-muted);
  margin-bottom: 16px;
}

.errors-content {
  display: flex;
  gap: 24px;
}

.errors-content.with-detail .errors-table-wrap {
  flex: 1;
  min-width: 0;
}

.errors-table-wrap {
  flex: 1;
}

.table-header-info {
  margin-bottom: 8px;
}

.total-count {
  font-size: 13px;
  color: var(--text-secondary);
}

.errors-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.errors-table th {
  text-align: left;
  padding: 10px 12px;
  color: var(--text-tertiary);
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-default);
  white-space: nowrap;
}

.errors-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}

.errors-table tbody tr {
  cursor: pointer;
  transition: background var(--transition-fast);
}

.errors-table tbody tr:hover {
  background: var(--bg-tertiary);
}

.errors-table tbody tr.selected {
  background: var(--accent-cyan-dim);
}

.col-time {
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-tertiary);
}

.col-message {
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary);
}

.source-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.source-badge.backend {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.source-badge.frontend {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.category-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  text-transform: capitalize;
}

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: capitalize;
}

.status-badge.new {
  background: var(--accent-amber-dim);
  color: var(--accent-amber);
}

.status-badge.investigating {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.status-badge.fixed {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.status-badge.ignored {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

/* Detail panel */
.detail-panel {
  width: 420px;
  flex-shrink: 0;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 250px);
  overflow: hidden;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.detail-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section h4 {
  margin: 0 0 8px 0;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
}

.detail-label {
  font-size: 12px;
  color: var(--text-tertiary);
  min-width: 80px;
  flex-shrink: 0;
}

.detail-value {
  font-size: 13px;
  color: var(--text-primary);
  word-break: break-all;
}

.error-message-block {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 12px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 150px;
  overflow-y: auto;
  margin: 0;
}

.collapse-toggle-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: pointer;
  padding: 0;
  margin-bottom: 8px;
}

.collapse-toggle-btn:hover {
  color: var(--text-primary);
}

.collapse-toggle-btn svg {
  transition: transform var(--transition-fast);
}

.collapse-toggle-btn svg.rotated {
  transform: rotate(90deg);
}

.stack-trace-block,
.context-block {
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 12px;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.fix-attempts-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fix-attempt-item {
  background: var(--bg-tertiary);
  border-radius: 6px;
  padding: 10px 12px;
}

.fix-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.fix-tier {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.fix-status-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
}

.fix-status-badge.pending {
  background: var(--accent-amber-dim);
  color: var(--accent-amber);
}

.fix-status-badge.running {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.fix-status-badge.success {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.fix-status-badge.failed {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.fix-action {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.fix-time {
  font-size: 11px;
  color: var(--text-tertiary);
}

.detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

@media (max-width: 900px) {
  .errors-content {
    flex-direction: column;
  }

  .detail-panel {
    width: 100%;
    max-height: 50vh;
  }
}
</style>
