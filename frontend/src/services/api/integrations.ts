import { apiFetch } from './client';

export interface Integration {
  id: string;
  trigger_id: string;
  type: string;
  name: string;
  config: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
}

export interface SlackStatus {
  id: string | null;
  name: string | null;
  connected: boolean;
}

export interface SlackCommandLog {
  id: string;
  user: string;
  channel: string;
  command: string;
  args: string;
  status: 'success' | 'running' | 'failed';
  timestamp: string;
  executionId?: string;
}

export const integrationApi = {
  list: () => apiFetch<Integration[]>('/admin/integrations'),
  get: (id: string) => apiFetch<Integration>(`/admin/integrations/${id}`),
  create: (data: Partial<Integration>) =>
    apiFetch<Integration>('/admin/integrations', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<Integration>) =>
    apiFetch<Integration>(`/admin/integrations/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    apiFetch<void>(`/admin/integrations/${id}`, { method: 'DELETE' }),
  test: (id: string) =>
    apiFetch<{ success: boolean; message: string }>(
      `/admin/integrations/${id}/test`,
      { method: 'POST' },
    ),
  listForTrigger: (triggerId: string) =>
    apiFetch<Integration[]>(`/admin/triggers/${triggerId}/integrations`),
};

// Slack-specific API
export const slackApi = {
  getStatus: () => apiFetch<SlackStatus>('/admin/integrations/slack/status'),

  listCommands: () =>
    apiFetch<Integration[]>('/admin/integrations?type=slack'),

  createCommand: (data: { name: string; config: Record<string, unknown>; trigger_id?: string; enabled?: boolean }) =>
    apiFetch<Integration>('/admin/integrations', {
      method: 'POST',
      body: JSON.stringify({ ...data, type: 'slack' }),
    }),

  updateCommand: (id: string, data: Partial<Pick<Integration, 'name' | 'config' | 'trigger_id' | 'enabled'>>) =>
    apiFetch<Integration>(`/admin/integrations/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  listCommandLogs: (limit = 50) => {
    const params = new URLSearchParams({
      entity_type: 'integration',
      entity_id: 'slack',
      limit: String(limit),
    });
    return apiFetch<{ events: Array<{
      id: string;
      action: string;
      entity_type: string;
      entity_id: string;
      outcome: string;
      actor: string;
      details: Record<string, unknown> | null;
      created_at: string;
    }>; total: number }>(`/api/audit/events/persistent?${params.toString()}`);
  },
};
