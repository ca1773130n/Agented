import { ref } from 'vue';
import { systemErrorApi } from '../services/api';
import type { SystemError, SystemErrorWithFixes, ErrorStatus, ErrorCategory, ErrorSource } from '../services/api/types/system';

export function useSystemErrors() {
  const errors = ref<SystemError[]>([]);
  const totalCount = ref(0);
  const selectedError = ref<SystemErrorWithFixes | null>(null);
  const isLoading = ref(false);
  const loadError = ref<string | null>(null);

  // Filters
  const statusFilter = ref<ErrorStatus | ''>('');
  const categoryFilter = ref<ErrorCategory | ''>('');
  const sourceFilter = ref<ErrorSource | ''>('');
  const searchQuery = ref('');
  const timeRange = ref<'hour' | 'day' | 'week' | 'all'>('day');

  // Counts for sidebar badge
  const newErrorCount = ref(0);

  let pollInterval: ReturnType<typeof setInterval> | null = null;

  function getSinceTimestamp(): string | undefined {
    const now = new Date();
    switch (timeRange.value) {
      case 'hour': return new Date(now.getTime() - 3600000).toISOString();
      case 'day': return new Date(now.getTime() - 86400000).toISOString();
      case 'week': return new Date(now.getTime() - 604800000).toISOString();
      default: return undefined;
    }
  }

  async function loadErrors() {
    isLoading.value = true;
    loadError.value = null;
    try {
      const params: Record<string, string | number> = {};
      if (statusFilter.value) params.status = statusFilter.value;
      if (categoryFilter.value) params.category = categoryFilter.value;
      if (sourceFilter.value) params.source = sourceFilter.value;
      if (searchQuery.value) params.search = searchQuery.value;
      const since = getSinceTimestamp();
      if (since) params.since = since;
      params.limit = 100;

      const result = await systemErrorApi.listErrors(params);
      errors.value = result.errors;
      totalCount.value = result.total_count;
    } catch (e) {
      loadError.value = e instanceof Error ? e.message : 'Failed to load errors';
    } finally {
      isLoading.value = false;
    }
  }

  async function selectError(errorId: string) {
    try {
      selectedError.value = await systemErrorApi.getError(errorId);
    } catch {
      selectedError.value = null;
    }
  }

  function clearSelection() {
    selectedError.value = null;
  }

  async function updateStatus(errorId: string, status: ErrorStatus) {
    await systemErrorApi.updateError(errorId, { status });
    await loadErrors();
    if (selectedError.value?.id === errorId) {
      await selectError(errorId);
    }
  }

  async function retryFix(errorId: string) {
    await systemErrorApi.retryFix(errorId);
    await loadErrors();
    if (selectedError.value?.id === errorId) {
      await selectError(errorId);
    }
  }

  async function pollNewCount() {
    try {
      const result = await systemErrorApi.getCounts();
      newErrorCount.value = result.counts?.new || 0;
    } catch {
      // Silently ignore polling failures
    }
  }

  function startPolling() {
    pollInterval = setInterval(() => {
      loadErrors();
    }, 10000);
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  return {
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
    newErrorCount,
    loadErrors,
    selectError,
    clearSelection,
    updateStatus,
    retryFix,
    pollNewCount,
    startPolling,
    stopPolling,
  };
}
