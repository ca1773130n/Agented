/**
 * Budget API module.
 */
import { apiFetch } from './client';
import type {
  WindowUsage,
  BudgetLimit,
  BudgetCheck,
  CostEstimate,
  TokenUsageRecord,
  UsageSummaryEntry,
  EntityUsageEntry,
  SessionStatsSummary,
  HistoryStatsResponse,
} from './types';

// Budget API
export const budgetApi = {
  getWindowUsage: async (): Promise<WindowUsage> => {
    return apiFetch<WindowUsage>('/admin/budgets/window-usage');
  },
  getLimits: async (): Promise<{ limits: BudgetLimit[] }> => {
    return apiFetch<{ limits: BudgetLimit[] }>('/admin/budgets/limits');
  },
  getLimit: async (entityType: string, entityId: string): Promise<BudgetLimit> => {
    return apiFetch<BudgetLimit>(`/admin/budgets/limits/${entityType}/${entityId}`);
  },
  setLimit: async (data: { entity_type: string; entity_id: string; period: string; soft_limit_usd?: number; hard_limit_usd?: number }): Promise<void> => {
    await apiFetch<void>('/admin/budgets/limits', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },
  deleteLimit: async (entityType: string, entityId: string): Promise<void> => {
    await apiFetch<void>(`/admin/budgets/limits/${entityType}/${entityId}`, {
      method: 'DELETE',
    });
  },
  checkBudget: async (entityType: string, entityId: string): Promise<BudgetCheck> => {
    return apiFetch<BudgetCheck>('/admin/budgets/check', {
      method: 'POST',
      body: JSON.stringify({ entity_type: entityType, entity_id: entityId }),
    });
  },
  estimateCost: async (prompt: string, model?: string): Promise<CostEstimate> => {
    return apiFetch<CostEstimate>('/admin/budgets/estimate', {
      method: 'POST',
      body: JSON.stringify({ prompt, model }),
    });
  },
  getUsage: async (params?: { entity_type?: string; entity_id?: string; start_date?: string; end_date?: string; limit?: number }): Promise<{ usage: TokenUsageRecord[]; total_cost_usd: number; total_records: number }> => {
    const query = params ? new URLSearchParams(params as Record<string, string>).toString() : '';
    return apiFetch<{ usage: TokenUsageRecord[]; total_cost_usd: number; total_records: number }>(`/admin/budgets/usage${query ? `?${query}` : ''}`);
  },
  getUsageSummary: async (params: { group_by: string; entity_type?: string; entity_id?: string; start_date?: string; end_date?: string }): Promise<{ summary: UsageSummaryEntry[] }> => {
    const query = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<{ summary: UsageSummaryEntry[] }>(`/admin/budgets/usage/summary?${query}`);
  },
  getUsageByEntity: async (params: { entity_type: string; period?: string; start_date?: string; end_date?: string }): Promise<{ entities: EntityUsageEntry[] }> => {
    const query = new URLSearchParams(params as Record<string, string>).toString();
    return apiFetch<{ entities: EntityUsageEntry[] }>(`/admin/budgets/usage/by-entity?${query}`);
  },
  collectSessions: () =>
    apiFetch<{ collected: { claude: { sessions: number; cost: number }; codex: { sessions: number; cost: number } } }>(
      '/admin/budgets/collect-sessions',
      { method: 'POST' }
    ),
  getAllTimeSpend: () =>
    apiFetch<{ total_cost_usd: number }>('/admin/budgets/usage/all-time'),
  getSessionStats: () =>
    apiFetch<{ stats: SessionStatsSummary | null; message?: string }>('/admin/budgets/session-stats'),
  getHistoryStats: async (params: { period?: string; months_back?: number }): Promise<HistoryStatsResponse> => {
    const query = new URLSearchParams();
    if (params.period) query.set('period', params.period);
    if (params.months_back) query.set('months_back', String(params.months_back));
    return apiFetch<HistoryStatsResponse>(`/admin/budgets/usage/history-stats?${query}`);
  },
};
