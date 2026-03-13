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
