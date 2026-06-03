<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ExecutionSearchResult } from '../services/api';
import { specializedBotApi, ApiError } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { sanitizeHighlight } from '../composables/useMarkdown';
const { t } = useI18n();

// FTS5 snippet() wraps matches in <mark> but does NOT HTML-escape the
// surrounding (agent-controlled) log text. Sanitize to <mark>-only before
// v-html as defense-in-depth (server also escapes — see execution_search_service).
function safeSnippet(value: string | null | undefined): string {
  return sanitizeHighlight(value || '');
}
const showToast = useToast();

const query = ref('');
const triggerId = ref('');
const results = ref<ExecutionSearchResult[]>([]);
const total = ref(0);
const searchedQuery = ref('');
const isLoading = ref(false);
const hasSearched = ref(false);

async function handleSearch() {
  const q = query.value.trim();
  if (!q) return;

  isLoading.value = true;
  hasSearched.value = true;
  searchedQuery.value = q;
  try {
    const response = await specializedBotApi.searchLogs(
      q,
      50,
      triggerId.value || undefined,
    );
    results.value = response.results;
    total.value = response.total;
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('executionSearch.searchFailed');
    showToast(message, 'error');
    results.value = [];
    total.value = 0;
  } finally {
    isLoading.value = false;
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') handleSearch();
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusClass(status: string): string {
  switch (status) {
    case 'success': return 'status-success';
    case 'failed': return 'status-failed';
    case 'running': return 'status-running';
    case 'cancelled':
    case 'interrupted': return 'status-cancelled';
    case 'timeout': return 'status-timeout';
    default: return 'status-idle';
  }
}
</script>

<template>
  <div class="execution-search">

    <PageHeader :title="t('executionSearch.title')" :subtitle="t('executionSearch.subtitle')" />

    <div class="search-controls">
      <div class="search-input-row">
        <input
          v-model="query"
          type="text"
          class="search-input"
          :placeholder="t('executionSearch.searchPlaceholder')"
          @keydown="handleKeydown"
        />
        <input
          v-model="triggerId"
          type="text"
          class="filter-input"
          :placeholder="t('executionSearch.filterPlaceholder')"
        />
        <button class="search-btn" :disabled="isLoading || !query.trim()" @click="handleSearch">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          {{ t('common.search') }}
        </button>
      </div>
    </div>

    <div v-if="isLoading" class="loading-state">
      <div class="spinner" />
      <span>{{ t('executionSearch.searching') }}</span>
    </div>

    <div v-else-if="!hasSearched" class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
      <p>{{ t('executionSearch.enterQuery') }}</p>
    </div>

    <div v-else-if="results.length === 0" class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <p>{{ t('executionSearch.noResults', { query: searchedQuery }) }}</p>
      <p class="hint">{{ t('executionSearch.tryDifferent') }}</p>
    </div>

    <div v-else class="results-section">
      <div class="results-header">
        {{ t('executionSearch.resultsCount', { count: total, query: searchedQuery }) }}
      </div>

      <div class="results-list">
        <div v-for="result in results" :key="result.execution_id" class="result-card">
          <div class="result-meta">
            <span class="result-trigger">{{ result.trigger_name || result.trigger_id }}</span>
            <span :class="['result-status', statusClass(result.status)]">{{ result.status }}</span>
            <span class="result-date">{{ formatDate(result.started_at) }}</span>
            <span class="result-id">{{ result.execution_id }}</span>
          </div>

          <!-- Snippets are sanitized to <mark>-only (safeSnippet); the raw log
               text is agent-controlled and must never reach the DOM unescaped. -->
          <div v-if="result.stdout_match" class="result-snippet">
            <span class="snippet-label">{{ t('executionSearch.stdout') }}</span>
            <span class="snippet-text" v-html="safeSnippet(result.stdout_match)"></span>
          </div>
          <div v-if="result.stderr_match" class="result-snippet">
            <span class="snippet-label">{{ t('executionSearch.stderr') }}</span>
            <span class="snippet-text" v-html="safeSnippet(result.stderr_match)"></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.execution-search {
  padding: 1.5rem 2rem;
  max-width: 1200px;
}

.search-controls {
  margin-bottom: 1.5rem;
}

.search-input-row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.search-input {
  flex: 1;
  padding: 0.625rem 0.875rem;
  background: var(--color-bg-secondary, #1a1a2e);
  border: 1px solid var(--color-border, #2a2a4a);
  border-radius: 6px;
  color: var(--color-text, #e0e0e0);
  font-size: 0.875rem;
}

.search-input:focus {
  outline: none;
  border-color: var(--color-primary, #6366f1);
}

.filter-input {
  width: 240px;
  padding: 0.625rem 0.875rem;
  background: var(--color-bg-secondary, #1a1a2e);
  border: 1px solid var(--color-border, #2a2a4a);
  border-radius: 6px;
  color: var(--color-text, #e0e0e0);
  font-size: 0.875rem;
}

.filter-input:focus {
  outline: none;
  border-color: var(--color-primary, #6366f1);
}

.search-btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.625rem 1rem;
  background: var(--color-primary, #6366f1);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.search-btn:hover:not(:disabled) {
  background: var(--color-primary-hover, #5558e6);
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 3rem 1rem;
  color: var(--color-text-muted, #888);
}

.loading-state .spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-border, #2a2a4a);
  border-top-color: var(--color-primary, #6366f1);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state svg {
  opacity: 0.4;
}

.empty-state p {
  margin: 0;
  font-size: 0.9375rem;
}

.empty-state .hint {
  font-size: 0.8125rem;
  opacity: 0.7;
}

.results-header {
  font-size: 0.8125rem;
  color: var(--color-text-muted, #888);
  margin-bottom: 0.75rem;
}

.results-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.result-card {
  background: var(--color-bg-secondary, #1a1a2e);
  border: 1px solid var(--color-border, #2a2a4a);
  border-radius: 8px;
  padding: 0.875rem 1rem;
}

.result-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
}

.result-trigger {
  font-weight: 600;
  font-size: 0.875rem;
  color: var(--color-text, #e0e0e0);
}

.result-status {
  font-size: 0.75rem;
  padding: 0.125rem 0.5rem;
  border-radius: 12px;
  font-weight: 500;
}

.status-success {
  background: rgba(52, 211, 153, 0.15);
  color: #34d399;
}

.status-failed {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.status-running {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

.status-cancelled {
  background: rgba(156, 163, 175, 0.15);
  color: #9ca3af;
}

.status-timeout {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.status-idle {
  background: rgba(156, 163, 175, 0.1);
  color: #6b7280;
}

.result-date {
  font-size: 0.75rem;
  color: var(--color-text-muted, #888);
}

.result-id {
  font-size: 0.6875rem;
  color: var(--color-text-muted, #666);
  font-family: monospace;
}

.result-snippet {
  margin-top: 0.375rem;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: var(--color-text-muted, #aaa);
}

.snippet-label {
  font-size: 0.6875rem;
  color: var(--color-text-muted, #666);
  margin-right: 0.375rem;
  text-transform: uppercase;
  font-weight: 600;
}

.snippet-text :deep(mark) {
  background: rgba(250, 204, 21, 0.3);
  color: #fbbf24;
  padding: 0 2px;
  border-radius: 2px;
}
</style>
