/**
 * Agent memory API module.
 * Provides thread-based message persistence, working memory, and semantic recall.
 */
import { apiFetch } from './client';

// --- Types ---

export interface MemoryThread {
  id: string;
  resource_id: string;
  resource_type: string;
  title: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface MemoryMessage {
  id: string;
  thread_id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  type: 'text' | 'tool_call' | 'tool_result';
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface WorkingMemory {
  entity_id: string;
  entity_type: string;
  content: string;
  template: string | null;
  content_parsed?: unknown;
  updated_at?: string;
}

export interface MemoryConfig {
  enabled: boolean;
  last_messages: number;
  semantic_recall: {
    enabled: boolean;
    top_k: number;
    message_range: number;
  };
  working_memory: {
    enabled: boolean;
    scope: 'agent' | 'thread';
    template: string;
  };
}

export interface ThreadListResponse {
  threads: MemoryThread[];
  total: number;
}

export interface MessageListResponse {
  messages: MemoryMessage[];
  total: number;
}

export interface RecallResponse {
  results: MemoryMessage[];
  count: number;
  query: string;
}

export interface SaveMessagesRequest {
  messages: Array<{
    role: string;
    content: string;
    type?: string;
    metadata?: Record<string, unknown>;
  }>;
}

// --- API ---

export const agentMemoryApi = {
  // Thread operations
  listThreads: (agentId: string) =>
    apiFetch<ThreadListResponse>(`/admin/agents/${agentId}/memory/threads`),

  createThread: (agentId: string, body: { title?: string; metadata?: Record<string, unknown> }) =>
    apiFetch<MemoryThread>(`/admin/agents/${agentId}/memory/threads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  getThread: (agentId: string, threadId: string) =>
    apiFetch<MemoryThread>(`/admin/agents/${agentId}/memory/threads/${threadId}`),

  deleteThread: (agentId: string, threadId: string) =>
    apiFetch<{ message: string }>(`/admin/agents/${agentId}/memory/threads/${threadId}`, {
      method: 'DELETE',
    }),

  // Message operations
  listMessages: (agentId: string, threadId: string) =>
    apiFetch<MessageListResponse>(
      `/admin/agents/${agentId}/memory/threads/${threadId}/messages`
    ),

  saveMessages: (agentId: string, threadId: string, body: SaveMessagesRequest) =>
    apiFetch<{ messages: MemoryMessage[]; count: number }>(
      `/admin/agents/${agentId}/memory/threads/${threadId}/messages`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }
    ),

  // Semantic recall
  recall: (agentId: string, query: string, threadId?: string, topK = 5, messageRange = 1) => {
    const params = new URLSearchParams({ q: query, top_k: String(topK), message_range: String(messageRange) });
    if (threadId) params.set('thread_id', threadId);
    return apiFetch<RecallResponse>(`/admin/agents/${agentId}/memory/recall?${params}`);
  },

  // Working memory
  getWorkingMemory: (agentId: string) =>
    apiFetch<WorkingMemory>(`/admin/agents/${agentId}/memory/working`),

  updateWorkingMemory: (agentId: string, body: { content: string; template?: string }) =>
    apiFetch<WorkingMemory>(`/admin/agents/${agentId}/memory/working`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  clearWorkingMemory: (agentId: string) =>
    apiFetch<{ message: string }>(`/admin/agents/${agentId}/memory/working`, {
      method: 'DELETE',
    }),

  // Memory config
  getConfig: (agentId: string) =>
    apiFetch<MemoryConfig>(`/admin/agents/${agentId}/memory/config`),

  updateConfig: (agentId: string, body: Partial<MemoryConfig>) =>
    apiFetch<MemoryConfig>(`/admin/agents/${agentId}/memory/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
};
