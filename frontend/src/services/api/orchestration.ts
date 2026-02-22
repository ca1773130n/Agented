/**
 * Orchestration API module.
 */
import { apiFetch } from './client';
import type {
  AccountHealth,
  FallbackChain,
  FallbackChainEntry,
} from './types';

// Orchestration API
export const orchestrationApi = {
  getHealth: async (): Promise<{ accounts: AccountHealth[] }> => {
    return apiFetch<{ accounts: AccountHealth[] }>('/admin/orchestration/health');
  },
  getFallbackChain: async (triggerId: string): Promise<{ chain: FallbackChain['entries'] }> => {
    return apiFetch<{ chain: FallbackChain['entries'] }>(`/admin/orchestration/triggers/${triggerId}/fallback-chain`);
  },
  setFallbackChain: async (triggerId: string, entries: FallbackChainEntry[]): Promise<void> => {
    await apiFetch<void>(`/admin/orchestration/triggers/${triggerId}/fallback-chain`, {
      method: 'PUT',
      body: JSON.stringify({ entries }),
    });
  },
  deleteFallbackChain: async (triggerId: string): Promise<void> => {
    await apiFetch<void>(`/admin/orchestration/triggers/${triggerId}/fallback-chain`, {
      method: 'DELETE',
    });
  },
  clearRateLimit: async (accountId: number): Promise<void> => {
    await apiFetch<void>(`/admin/orchestration/accounts/${accountId}/clear-rate-limit`, {
      method: 'POST',
    });
  },
};
