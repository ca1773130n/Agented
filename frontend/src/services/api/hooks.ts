/**
 * Hook and hook conversation API modules.
 */
import { API_BASE, apiFetch } from './client';
import type {
  Hook,
  HookEvent,
  HookConversation,
  DesignConversationSummary,
} from './types';

// Hook API
export const hookApi = {
  list: (projectId?: string, pagination?: { limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (projectId) params.set('project_id', projectId);
    if (pagination?.limit != null) params.set('limit', String(pagination.limit));
    if (pagination?.offset != null) params.set('offset', String(pagination.offset));
    const query = params.toString();
    return apiFetch<{ hooks: Hook[]; total_count?: number }>(`/admin/hooks${query ? `?${query}` : ''}`);
  },

  get: (hookId: number) => apiFetch<Hook>(`/admin/hooks/${hookId}`),

  create: (data: {
    name: string;
    event: HookEvent;
    description?: string;
    content?: string;
    enabled?: boolean;
    project_id?: string;
    source_path?: string;
  }) => apiFetch<{ message: string; hook: Hook }>('/admin/hooks', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (hookId: number, data: Partial<{
    name: string;
    event: HookEvent;
    description: string;
    content: string;
    enabled: boolean;
    project_id: string | undefined;
    source_path: string | undefined;
  }>) => apiFetch<Hook>(`/admin/hooks/${hookId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (hookId: number) => apiFetch<{ message: string }>(`/admin/hooks/${hookId}`, {
    method: 'DELETE',
  }),

  listByProject: (projectId: string) =>
    apiFetch<{ hooks: Hook[]; project_id: string }>(`/admin/hooks/project/${projectId}`),

  listByEvent: (event: HookEvent) =>
    apiFetch<{ hooks: Hook[]; event: string }>(`/admin/hooks/event/${event}`),
};

// Hook Conversation API
export const hookConversationApi = {
  list: () => apiFetch<{ conversations: DesignConversationSummary[] }>('/api/hooks/conversations/'),
  start: () => apiFetch<{ conversation_id: string; message: string }>('/api/hooks/conversations/start', { method: 'POST' }),
  get: (convId: string) => apiFetch<HookConversation>(`/api/hooks/conversations/${convId}`),
  sendMessage: (convId: string, message: string, options?: { backend?: string; account_id?: string; model?: string }) => apiFetch<{ message_id: string; status: string }>(`/api/hooks/conversations/${convId}/message`, { method: 'POST', body: JSON.stringify({ message, ...options }) }),
  stream: (convId: string): EventSource => new EventSource(`${API_BASE}/api/hooks/conversations/${convId}/stream`),
  finalize: (convId: string) => apiFetch<{ message: string; hook_id: number; hook: Hook }>(`/api/hooks/conversations/${convId}/finalize`, { method: 'POST' }),
  resume: (convId: string) => apiFetch<{ message: string; conversation_id: string }>(`/api/hooks/conversations/${convId}/resume`, { method: 'POST' }),
  abandon: (convId: string) => apiFetch<{ message: string }>(`/api/hooks/conversations/${convId}/abandon`, { method: 'POST' }),
};
