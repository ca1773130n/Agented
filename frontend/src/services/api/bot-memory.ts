/**
 * Bot memory store API module.
 * Provides per-bot persistent key-value memory CRUD operations.
 */
import { apiFetch } from './client';

export interface MemoryEntry {
  bot_id: string;
  key: string;
  value: string;
  source: 'bot' | 'manual';
  expires_at: string | null;
  updated_at: string;
  used_bytes?: number;
  max_bytes?: number;
}

export interface BotMemorySummary {
  bot_id: string;
  bot_name: string;
  entry_count: number;
  used_bytes: number;
}

export interface BotMemoryListAllResponse {
  bots: BotMemorySummary[];
  total: number;
}

export interface BotMemoryResponse {
  bot_id: string;
  entries: MemoryEntry[];
  used_bytes: number;
  max_bytes: number;
}

export interface UpsertMemoryEntryRequest {
  value: string;
  expiresAt?: string | null;
}

export const botMemoryApi = {
  /** List all bots that have memory entries. */
  listAll: () =>
    apiFetch<BotMemoryListAllResponse>('/admin/bots/memory'),

  /** Get all memory entries for a specific bot. */
  getBotMemory: (botId: string) =>
    apiFetch<BotMemoryResponse>(`/admin/bots/${botId}/memory`),

  /** Create or update a memory entry. */
  upsertEntry: (botId: string, key: string, body: UpsertMemoryEntryRequest) =>
    apiFetch<MemoryEntry>(`/admin/bots/${botId}/memory/${encodeURIComponent(key)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  /** Delete a single memory entry. */
  deleteEntry: (botId: string, key: string) =>
    apiFetch<{ message: string }>(`/admin/bots/${botId}/memory/${encodeURIComponent(key)}`, {
      method: 'DELETE',
    }),

  /** Delete all memory entries for a bot. */
  clearAll: (botId: string) =>
    apiFetch<{ message: string }>(`/admin/bots/${botId}/memory`, {
      method: 'DELETE',
    }),
};
