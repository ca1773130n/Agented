/**
 * Specialized bot management and execution search API module.
 */
import { apiFetch } from './client';
import type {
  SpecializedBotStatus,
  SpecializedBotHealth,
  ExecutionSearchResponse,
  ExecutionSearchStats,
} from './types';

export const specializedBotApi = {
  /** Get availability status of all specialized bots. */
  getStatus: () =>
    apiFetch<{ bots: SpecializedBotStatus[] }>('/admin/specialized-bots/status'),

  /** Get health status of external dependencies needed by bots. */
  getHealth: () =>
    apiFetch<SpecializedBotHealth>('/admin/specialized-bots/health'),

  /** Search execution logs using natural language queries with BM25 ranking. */
  searchLogs: (query: string, limit?: number, triggerId?: string) => {
    const params = new URLSearchParams({ q: query });
    if (limit !== undefined) params.set('limit', String(limit));
    if (triggerId) params.set('trigger_id', triggerId);
    return apiFetch<ExecutionSearchResponse>(
      `/admin/execution-search?${params.toString()}`
    );
  },

  /** Get statistics about the execution log search index. */
  getSearchStats: () =>
    apiFetch<ExecutionSearchStats>('/admin/execution-search/stats'),
};
