/**
 * Rule and rule conversation API modules.
 */
import { API_BASE, apiFetch } from './client';
import type {
  Rule,
  RuleType,
  RuleConversation,
  DesignConversationSummary,
} from './types';

// Rule API
export const ruleApi = {
  list: (projectId?: string, pagination?: { limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (projectId) params.set('project_id', projectId);
    if (pagination?.limit != null) params.set('limit', String(pagination.limit));
    if (pagination?.offset != null) params.set('offset', String(pagination.offset));
    const query = params.toString();
    return apiFetch<{ rules: Rule[]; total_count?: number }>(`/admin/rules${query ? `?${query}` : ''}`);
  },

  get: (ruleId: number) => apiFetch<Rule>(`/admin/rules/${ruleId}`),

  create: (data: {
    name: string;
    rule_type?: RuleType;
    description?: string;
    condition?: string;
    action?: string;
    enabled?: boolean;
    project_id?: string;
    source_path?: string;
  }) => apiFetch<{ message: string; rule: Rule }>('/admin/rules', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (ruleId: number, data: Partial<{
    name: string;
    rule_type: RuleType;
    description: string;
    condition: string;
    action: string;
    enabled: boolean;
    project_id: string | undefined;
  }>) => apiFetch<Rule>(`/admin/rules/${ruleId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (ruleId: number) => apiFetch<{ message: string }>(`/admin/rules/${ruleId}`, {
    method: 'DELETE',
  }),

  listByProject: (projectId: string) =>
    apiFetch<{ rules: Rule[]; project_id: string }>(`/admin/rules/project/${projectId}`),

  listByType: (ruleType: RuleType) =>
    apiFetch<{ rules: Rule[]; rule_type: string }>(`/admin/rules/type/${ruleType}`),

  export: (ruleId: number) =>
    apiFetch<{ rule: Partial<Rule>; format: string }>(`/admin/rules/${ruleId}/export`),
};

// Rule Conversation API
export const ruleConversationApi = {
  list: () => apiFetch<{ conversations: DesignConversationSummary[] }>('/api/rules/conversations/'),
  start: () => apiFetch<{ conversation_id: string; message: string }>('/api/rules/conversations/start', { method: 'POST' }),
  get: (convId: string) => apiFetch<RuleConversation>(`/api/rules/conversations/${convId}`),
  sendMessage: (convId: string, message: string, options?: { backend?: string; account_id?: string; model?: string }) => apiFetch<{ message_id: string; status: string }>(`/api/rules/conversations/${convId}/message`, { method: 'POST', body: JSON.stringify({ message, ...options }) }),
  stream: (convId: string): EventSource => new EventSource(`${API_BASE}/api/rules/conversations/${convId}/stream`),
  finalize: (convId: string) => apiFetch<{ message: string; rule_id: number; rule: Rule }>(`/api/rules/conversations/${convId}/finalize`, { method: 'POST' }),
  resume: (convId: string) => apiFetch<{ message: string; conversation_id: string }>(`/api/rules/conversations/${convId}/resume`, { method: 'POST' }),
  abandon: (convId: string) => apiFetch<{ message: string }>(`/api/rules/conversations/${convId}/abandon`, { method: 'POST' }),
};
