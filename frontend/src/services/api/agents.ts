/**
 * Agent and agent conversation API modules.
 */
import { API_BASE, apiFetch } from './client';
import type {
  Agent,
  AgentConversation,
  EffortLevel,
} from './types';

// Agent API
export const agentApi = {
  list: (params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiFetch<{ agents: Agent[]; total_count?: number }>(`/admin/agents${query ? `?${query}` : ''}`);
  },

  get: (agentId: string) => apiFetch<Agent>(`/admin/agents/${agentId}`),

  create: (data: {
    name: string;
    description?: string;
    role?: string;
    goals?: string;
    context?: string;
    backend_type?: 'claude' | 'opencode' | 'gemini' | 'codex';
    skills?: string;
    documents?: string;
    system_prompt?: string;
    preferred_model?: string;
    effort_level?: EffortLevel;
    creation_conversation_id?: string;
  }) => apiFetch<{ message: string; agent_id: string; name: string }>('/admin/agents', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (agentId: string, data: Partial<{
    name: string;
    description: string;
    role: string;
    goals: string;
    context: string;
    backend_type: 'claude' | 'opencode' | 'gemini' | 'codex';
    enabled: number;
    skills: string;
    documents: string;
    system_prompt: string;
    preferred_model: string;
    effort_level: EffortLevel;
  }>) => apiFetch<{ message: string }>(`/admin/agents/${agentId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (agentId: string) => apiFetch<{ message: string }>(`/admin/agents/${agentId}`, {
    method: 'DELETE',
  }),

  run: (agentId: string, message?: string) =>
    apiFetch<{ message: string; agent_id: string; execution_id: string; status: string }>(`/admin/agents/${agentId}/run`, {
      method: 'POST',
      body: JSON.stringify({ message: message || '' }),
    }),

  export: (agentId: string) =>
    apiFetch<{ filename: string; content: string; agent_id: string; agent_name: string }>(`/admin/agents/${agentId}/export`),
};

// Agent Conversation API
export const agentConversationApi = {
  start: () => apiFetch<{ conversation_id: string; message: string }>('/api/agents/conversations/start', {
    method: 'POST',
  }),

  get: (convId: string) => apiFetch<AgentConversation>(`/api/agents/conversations/${convId}`),

  sendMessage: (convId: string, message: string, options?: { backend?: string; account_id?: string; model?: string }) =>
    apiFetch<{ message_id: string; status: string }>(`/api/agents/conversations/${convId}/message`, {
      method: 'POST',
      body: JSON.stringify({ message, ...options }),
    }),

  stream: (convId: string): EventSource => {
    return new EventSource(`${API_BASE}/api/agents/conversations/${convId}/stream`);
  },

  finalize: (convId: string) =>
    apiFetch<{ message: string; agent_id: string; agent: Agent }>(`/api/agents/conversations/${convId}/finalize`, {
      method: 'POST',
    }),

  abandon: (convId: string) =>
    apiFetch<{ message: string }>(`/api/agents/conversations/${convId}/abandon`, {
      method: 'POST',
    }),
};
