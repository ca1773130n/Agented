import { apiFetch, ApiError } from './client';

// === types ===

export interface MemoryThread {
  id: string;
  resource_id: string;
  resource_type: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown> | null;
  message_count?: number; // populated by getThread
}

export interface MemoryMessage {
  id: string;
  thread_id: string;
  role: string;
  content: string;
  type?: string;
  metadata?: Record<string, unknown> | null;
  created_at: string;
}

export interface WorkingMemory {
  entity_id: string;
  entity_type: string;
  content: string;
  content_parsed?: Record<string, unknown> | null;
  template?: string | null;
  updated_at?: string;
}

export interface RecallResponse {
  results: MemoryMessage[];
  count: number;
  query: string;
  search_mode: string;
  relevance_score: number;
}

export interface ListThreadsParams {
  limit?: number;
  offset?: number;
}

export interface ListThreadsResponse {
  threads: MemoryThread[];
  total: number;
}

export interface ListMessagesResponse {
  messages: MemoryMessage[];
  total: number;
}

// === REST client ===

export const agentMemoryApi = {
  async listThreads(
    agentId: string,
    params: ListThreadsParams = {},
  ): Promise<ListThreadsResponse> {
    const qs = new URLSearchParams();
    if (params.limit != null) qs.set('limit', String(params.limit));
    if (params.offset != null) qs.set('offset', String(params.offset));
    const tail = qs.toString() ? `?${qs.toString()}` : '';
    return apiFetch(
      `/admin/agents/${encodeURIComponent(agentId)}/memory/threads${tail}`,
    );
  },

  async getThread(agentId: string, threadId: string): Promise<MemoryThread> {
    return apiFetch(
      `/admin/agents/${encodeURIComponent(agentId)}/memory/threads/${encodeURIComponent(threadId)}`,
    );
  },

  async getMessages(agentId: string, threadId: string): Promise<ListMessagesResponse> {
    return apiFetch(
      `/admin/agents/${encodeURIComponent(agentId)}/memory/threads/${encodeURIComponent(threadId)}/messages`,
    );
  },

  /**
   * Returns the working memory blob. The backend always returns an
   * object — if the entity has no working memory yet, `content` is an
   * empty string. Callers can treat empty-content as "no working
   * memory".
   */
  async getWorkingMemory(agentId: string): Promise<WorkingMemory> {
    return apiFetch(
      `/admin/agents/${encodeURIComponent(agentId)}/memory/working`,
    );
  },

  /**
   * FTS5 recall search. The backend returns RecallResponse; we don't
   * expose vector / hybrid modes in v0.5.11 — fts is the default.
   */
  async recall(
    agentId: string,
    query: string,
    topK: number = 5,
  ): Promise<RecallResponse> {
    const qs = new URLSearchParams({ q: query, top_k: String(topK) });
    return apiFetch(
      `/admin/agents/${encodeURIComponent(agentId)}/memory/recall?${qs.toString()}`,
    );
  },
};

export { ApiError };
