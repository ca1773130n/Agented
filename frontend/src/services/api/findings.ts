/**
 * Findings triage API module.
 */
import { apiFetch } from './client';

export interface TriageFinding {
  id: string;
  title: string;
  description: string | null;
  severity: string;
  status: string;
  bot_id: string | null;
  file_ref: string | null;
  owner: string | null;
  execution_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface FindingsListResponse {
  findings: TriageFinding[];
}

export interface CreateFindingRequest {
  title: string;
  description?: string;
  severity: string;
  bot_id?: string;
  file_ref?: string;
  owner?: string;
  execution_id?: string;
}

export interface UpdateFindingRequest {
  status?: string;
  owner?: string;
}

export const findingsApi = {
  list: (params?: { status?: string; bot_id?: string; owner?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.bot_id) query.set('bot_id', params.bot_id);
    if (params?.owner) query.set('owner', params.owner);
    const qs = query.toString();
    return apiFetch<FindingsListResponse>(`/api/findings${qs ? `?${qs}` : ''}`);
  },

  create: (data: CreateFindingRequest) =>
    apiFetch<TriageFinding>('/api/findings', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: UpdateFindingRequest) =>
    apiFetch<TriageFinding>(`/api/findings/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  remove: (id: string) =>
    apiFetch<void>(`/api/findings/${id}`, { method: 'DELETE' }),
};
