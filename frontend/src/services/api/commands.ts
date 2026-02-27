/**
 * Command and command conversation API modules.
 */
import { API_BASE, apiFetch, createAuthenticatedEventSource } from './client';
import type { AuthenticatedEventSource } from './client';
import type {
  Command,
  CommandConversation,
  DesignConversationSummary,
} from './types';

// Command API
export const commandApi = {
  list: (projectId?: string, pagination?: { limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (projectId) params.set('project_id', projectId);
    if (pagination?.limit != null) params.set('limit', String(pagination.limit));
    if (pagination?.offset != null) params.set('offset', String(pagination.offset));
    const query = params.toString();
    return apiFetch<{ commands: Command[]; total_count?: number }>(`/admin/commands${query ? `?${query}` : ''}`);
  },

  get: (commandId: number) => apiFetch<Command>(`/admin/commands/${commandId}`),

  create: (data: {
    name: string;
    description?: string;
    content?: string;
    arguments?: string;
    enabled?: boolean;
    project_id?: string;
    source_path?: string;
  }) => apiFetch<{ message: string; command: Command }>('/admin/commands', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (commandId: number, data: Partial<{
    name: string;
    description: string;
    content: string;
    arguments: string;
    enabled: boolean;
    project_id: string | undefined;
  }>) => apiFetch<Command>(`/admin/commands/${commandId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (commandId: number) => apiFetch<{ message: string }>(`/admin/commands/${commandId}`, {
    method: 'DELETE',
  }),

  listByProject: (projectId: string) =>
    apiFetch<{ commands: Command[]; project_id: string }>(`/admin/commands/project/${projectId}`),
};

// Command Conversation API
export const commandConversationApi = {
  list: () => apiFetch<{ conversations: DesignConversationSummary[] }>('/api/commands/conversations/'),
  start: () => apiFetch<{ conversation_id: string; message: string }>('/api/commands/conversations/start', { method: 'POST' }),
  get: (convId: string) => apiFetch<CommandConversation>(`/api/commands/conversations/${convId}`),
  sendMessage: (convId: string, message: string, options?: { backend?: string; account_id?: string; model?: string }) => apiFetch<{ message_id: string; status: string }>(`/api/commands/conversations/${convId}/message`, { method: 'POST', body: JSON.stringify({ message, ...options }) }),
  stream: (convId: string): AuthenticatedEventSource => createAuthenticatedEventSource(`${API_BASE}/api/commands/conversations/${convId}/stream`),
  finalize: (convId: string) => apiFetch<{ message: string; command_id: number; command: Command }>(`/api/commands/conversations/${convId}/finalize`, { method: 'POST' }),
  resume: (convId: string) => apiFetch<{ message: string; conversation_id: string }>(`/api/commands/conversations/${convId}/resume`, { method: 'POST' }),
  abandon: (convId: string) => apiFetch<{ message: string }>(`/api/commands/conversations/${convId}/abandon`, { method: 'POST' }),
};
