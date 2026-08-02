<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { useSystemErrors } from '../composables/useSystemErrors';
import { settingsApi } from '../services/api';
import type { SystemError } from '../services/api/types/system';
import { safeFormatDateTime } from '../utils/datetime';

const { t } = useI18n();
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

// Which backend Tier-2 autofix spends on. It runs unattended and edits the
// working tree, so the operator gets to choose — this used to be hardcoded to
// claude with no way to change it. Mirrors `_AUTOFIX_BACKENDS` in
// autofix_service.py; the server re-validates and falls back on its own, so a
// stale tab cannot make it launch something unrecognised.
const AUTOFIX_BACKENDS = ['codex', 'claude', 'gemini', 'opencode'] as const;
type AutofixBackend = (typeof AUTOFIX_BACKENDS)[number];
const AUTOFIX_BACKEND_DEFAULT: AutofixBackend = 'codex';

// The server-confirmed value, and ONLY ever that — the select is bound with
// `:value`, not `v-model`, so a choice becomes state after it is stored rather
// than before. With v-model the ref moved first and a refused change left the
// control displaying a backend nobody saved; putting the ref back did not fix
// it either, because Vue skips patching a <select> whose bound value did not
// change between renders, leaving the DOM on the refused option.
const autofixBackend = ref<AutofixBackend>(AUTOFIX_BACKEND_DEFAULT);
// Null until a read succeeds. A failed read must not render as "codex" — the
// server may well be billing opencode, and a confident wrong answer on this
// control is worse than an obvious blank.
const autofixReadFailed = ref(false);
const savingAutofixBackend = ref(false);
// The control stays disabled until the stored value has loaded. That is what
// closes the stale-read race: a slow GET landing after the operator had already
// saved would otherwise stamp the old value back over their choice, silently,
// on a control that says which account gets billed. Disabled-while-loading
// makes that collision unreachable, so no request-sequencing token is needed —
// the operator cannot touch the select while a read is in flight, and a save
// disables it again for the duration of the write.
const loadingAutofixBackend = ref(true);

function asAutofixBackend(value: string | null | undefined): AutofixBackend | null {
  const v = (value || '').trim().toLowerCase();
  return (AUTOFIX_BACKENDS as readonly string[]).includes(v) ? (v as AutofixBackend) : null;
}

async function loadAutofixBackend() {
  loadingAutofixBackend.value = true;
  try {
    const { value } = await settingsApi.get('autofix_backend');
    // Unset is the normal first-run state, not an error: the server applies the
    // same default, so showing it is accurate rather than a guess.
    autofixBackend.value = asAutofixBackend(value) ?? AUTOFIX_BACKEND_DEFAULT;
    autofixReadFailed.value = false;
  } catch {
    // Do NOT fall back to the default here. The stored value is unknown, and
    // rendering "codex" would state, on a control about billing, something the
    // server may flatly contradict. Say so and stay locked instead.
    autofixReadFailed.value = true;
  } finally {
    loadingAutofixBackend.value = false;
  }
}

async function onChangeAutofixBackend(event: Event) {
  const el = event.target as HTMLSelectElement;
  /** Put the visible control back to what the server actually holds. */
  const revert = () => {
    el.value = autofixBackend.value;
  };

  // `disabled` on the select is UX, not a guarantee: it stops a person, but a
  // dispatched change event still reaches this handler. Without a logical
  // guard, a save issued while the initial GET is in flight would be overwritten
  // when that GET resolves — leaving the control showing one backend and the
  // server holding another. Refuse instead; the operator's next change is a
  // click away, and a silent disagreement here is about billing.
  const chosen = asAutofixBackend(el.value);
  if (
    loadingAutofixBackend.value ||
    savingAutofixBackend.value ||
    autofixReadFailed.value ||
    !chosen
  ) {
    revert();
    return;
  }

  savingAutofixBackend.value = true;
  try {
    await settingsApi.set('autofix_backend', chosen);
    autofixBackend.value = chosen;
    showToast(t('systemErrors.autofix.saved', { backend: chosen }), 'success');
  } catch {
    showToast(t('systemErrors.autofix.saveFailed'), 'error');
    // Never leave the control showing a backend that was not saved — this
    // dropdown is a claim about which account is about to be billed.
    revert();
  } finally {
    savingAutofixBackend.value = false;
  }
}

function relativeTime(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 60000) return t('systemErrors.time.justNow');
  if (diff < 3600000) return t('systemErrors.time.minutesAgo', { n: Math.floor(diff / 60000) });
  if (diff < 86400000) return t('systemErrors.time.hoursAgo', { n: Math.floor(diff / 3600000) });
  return t('systemErrors.time.daysAgo', { n: Math.floor(diff / 86400000) });
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
    showToast(t('systemErrors.toast.statusUpdated', { status }), 'success');
  } catch {
    showToast(t('systemErrors.toast.statusFailed'), 'error');
  }
}

async function onRetryFix() {
  if (!selectedError.value) return;
  try {
    await retryFix(selectedError.value.id);
    showToast(t('systemErrors.toast.retryInitiated'), 'success');
  } catch {
    showToast(t('systemErrors.toast.retryFailed'), 'error');
  }
}

function applyFilters() {
  loadErrors();
}

onMounted(() => {
  loadErrors();
  loadAutofixBackend();
  startPolling();
});

onUnmounted(() => {
  stopPolling();
});
</script>

<template>
  <div class="system-errors-page">
    <PageHeader :title="t('systemErrors.title')" :subtitle="t('systemErrors.subtitle')" />

    <!-- Autofix backend. A setting, not a filter — it decides which account the
         unattended Tier-2 investigation spends on. -->
    <div class="autofix-bar">
      <label for="autofix-backend">{{ t('systemErrors.autofix.label') }}</label>
      <select
        id="autofix-backend"
        :value="autofixBackend"
        :disabled="savingAutofixBackend || loadingAutofixBackend || autofixReadFailed"
        @change="onChangeAutofixBackend"
      >
        <option value="codex">Codex</option>
        <option value="claude">Claude</option>
        <option value="gemini">Gemini (Antigravity)</option>
        <option value="opencode">OpenCode</option>
      </select>
      <button v-if="autofixReadFailed" type="button" class="autofix-retry" @click="loadAutofixBackend">
        {{ t('systemErrors.autofix.retry') }}
      </button>
      <p class="autofix-hint">
        {{ autofixReadFailed ? t('systemErrors.autofix.readFailed') : t('systemErrors.autofix.hint') }}
      </p>
    </div>

    <!-- Filters -->
    <div class="filters-bar">
      <div class="filter-group">
        <label>{{ t('systemErrors.filters.status') }}</label>
        <select v-model="statusFilter" @change="applyFilters">
          <option value="">{{ t('systemErrors.filters.all') }}</option>
          <option value="new">{{ t('systemErrors.status.new') }}</option>
          <option value="investigating">{{ t('systemErrors.status.investigating') }}</option>
          <option value="fixed">{{ t('systemErrors.status.fixed') }}</option>
          <option value="ignored">{{ t('systemErrors.status.ignored') }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label>{{ t('systemErrors.filters.category') }}</label>
        <select v-model="categoryFilter" @change="applyFilters">
          <option value="">{{ t('systemErrors.filters.all') }}</option>
          <option value="cli_error">{{ t('systemErrors.category.cliError') }}</option>
          <option value="proxy_error">{{ t('systemErrors.category.proxyError') }}</option>
          <option value="streaming_error">{{ t('systemErrors.category.streamingError') }}</option>
          <option value="runtime_error">{{ t('systemErrors.category.runtimeError') }}</option>
          <option value="frontend_error">{{ t('systemErrors.category.frontendError') }}</option>
          <option value="db_error">{{ t('systemErrors.category.dbError') }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label>{{ t('systemErrors.filters.source') }}</label>
        <select v-model="sourceFilter" @change="applyFilters">
          <option value="">{{ t('systemErrors.filters.all') }}</option>
          <option value="backend">{{ t('systemErrors.source.backend') }}</option>
          <option value="frontend">{{ t('systemErrors.source.frontend') }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label>{{ t('systemErrors.filters.time') }}</label>
        <select v-model="timeRange" @change="applyFilters">
          <option value="hour">{{ t('systemErrors.time.lastHour') }}</option>
          <option value="day">{{ t('systemErrors.time.last24h') }}</option>
          <option value="week">{{ t('systemErrors.time.lastWeek') }}</option>
          <option value="all">{{ t('systemErrors.time.allTime') }}</option>
        </select>
      </div>
      <div class="filter-group search-group">
        <input
          v-model="searchQuery"
          type="text"
          :placeholder="t('systemErrors.searchPlaceholder')"
          class="search-input"
          @keyup.enter="applyFilters"
        />
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading && !errors.length" class="state-container">
      <div class="spinner"></div>
      <p class="state-message">{{ t('systemErrors.loading') }}</p>
    </div>

    <!-- Error State -->
    <div v-else-if="loadError" class="state-container state-error">
      <p class="state-title">{{ t('systemErrors.loadFailedTitle') }}</p>
      <p class="state-message">{{ loadError }}</p>
      <div class="state-action">
        <button class="btn-retry" @click="loadErrors">{{ t('common.retry') }}</button>
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
      <p class="state-title">{{ t('systemErrors.empty.title') }}</p>
      <p class="state-message">{{ t('systemErrors.empty.message') }}</p>
    </div>

    <!-- Content: table + detail -->
    <div v-else class="errors-content" :class="{ 'with-detail': selectedError }">
      <div class="errors-table-wrap">
        <div class="table-header-info">
          <span class="total-count">{{ t('systemErrors.errorCount', { count: totalCount }) }}</span>
        </div>
        <table class="errors-table">
          <thead>
            <tr>
              <th>{{ t('systemErrors.table.time') }}</th>
              <th>{{ t('systemErrors.table.source') }}</th>
              <th>{{ t('systemErrors.table.category') }}</th>
              <th>{{ t('systemErrors.table.message') }}</th>
              <th>{{ t('systemErrors.table.status') }}</th>
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
          <h3>{{ t('systemErrors.detail.title') }}</h3>
          <button class="btn btn-sm" @click="clearSelection">{{ t('common.close') }}</button>
        </div>

        <div class="detail-body">
          <div class="detail-section">
            <div class="detail-row">
              <span class="detail-label">{{ t('systemErrors.detail.id') }}</span>
              <span class="detail-value text-mono">{{ selectedError.id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">{{ t('systemErrors.detail.timestamp') }}</span>
              <span class="detail-value">{{ safeFormatDateTime(selectedError.timestamp) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">{{ t('systemErrors.detail.source') }}</span>
              <span class="source-badge" :class="selectedError.source">{{ selectedError.source }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">{{ t('systemErrors.detail.category') }}</span>
              <span class="category-badge">{{ selectedError.category }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">{{ t('systemErrors.detail.status') }}</span>
              <span class="status-badge" :class="selectedError.status">{{ selectedError.status }}</span>
            </div>
            <div v-if="selectedError.request_id" class="detail-row">
              <span class="detail-label">{{ t('systemErrors.detail.requestId') }}</span>
              <span class="detail-value text-mono">{{ selectedError.request_id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">{{ t('systemErrors.detail.hash') }}</span>
              <span class="detail-value text-mono">{{ selectedError.error_hash }}</span>
            </div>
          </div>

          <div class="detail-section">
            <h4>{{ t('systemErrors.detail.message') }}</h4>
            <pre class="error-message-block">{{ selectedError.message }}</pre>
          </div>

          <div v-if="selectedError.stack_trace" class="detail-section">
            <button class="collapse-toggle-btn" @click="stackTraceExpanded = !stackTraceExpanded">
              <svg :class="{ rotated: stackTraceExpanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <polyline points="9,18 15,12 9,6"/>
              </svg>
              {{ t('systemErrors.detail.stackTrace') }}
            </button>
            <pre v-show="stackTraceExpanded" class="stack-trace-block">{{ selectedError.stack_trace }}</pre>
          </div>

          <div v-if="selectedError.context_json" class="detail-section">
            <button class="collapse-toggle-btn" @click="contextExpanded = !contextExpanded">
              <svg :class="{ rotated: contextExpanded }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <polyline points="9,18 15,12 9,6"/>
              </svg>
              {{ t('systemErrors.detail.context') }}
            </button>
            <pre v-show="contextExpanded" class="context-block">{{ selectedError.context_json }}</pre>
          </div>

          <!-- Fix attempts -->
          <div v-if="selectedError.fix_attempts?.length" class="detail-section">
            <h4>{{ t('systemErrors.detail.fixAttempts') }}</h4>
            <div class="fix-attempts-list">
              <div v-for="fix in selectedError.fix_attempts" :key="fix.id" class="fix-attempt-item">
                <div class="fix-row">
                  <span class="fix-tier">{{ t('systemErrors.detail.tier', { tier: fix.tier }) }}</span>
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
              {{ t('systemErrors.actions.investigate') }}
            </button>
            <button
              v-if="selectedError.status !== 'fixed'"
              class="btn btn-sm btn-primary"
              @click="onRetryFix()"
            >
              {{ t('systemErrors.actions.retryFix') }}
            </button>
            <button
              v-if="selectedError.status !== 'ignored'"
              class="btn btn-sm"
              @click="onUpdateStatus('ignored')"
            >
              {{ t('systemErrors.actions.ignore') }}
            </button>
            <button
              v-if="selectedError.status !== 'fixed'"
              class="btn btn-sm"
              style="background: var(--accent-emerald-dim); color: var(--accent-emerald);"
              @click="onUpdateStatus('fixed')"
            >
              {{ t('systemErrors.actions.markFixed') }}
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

.autofix-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border-default);
}

.autofix-bar label {
  font-size: 13px;
  color: var(--text-secondary);
}

.autofix-hint {
  margin: 0;
  flex: 1;
  min-width: 200px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.autofix-retry {
  padding: 4px 10px;
  font-size: 12px;
  font-family: inherit;
  color: var(--text-primary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
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
