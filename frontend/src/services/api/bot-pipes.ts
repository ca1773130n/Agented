/**
 * Bot output piping API module.
 */
import { apiFetch } from './client';

export interface BotPipe {
  id: string;
  name: string;
  source_bot_id: string;
  dest_bot_id: string;
  transform: 'passthrough' | 'trim' | 'json-extract';
  enabled: boolean | number;
  created_at: string;
}

export interface BotPipeExecution {
  id: string;
  pipe_id: string;
  pipe_name: string;
  triggered_at: string;
  source_preview: string | null;
  destination_status: 'pending' | 'running' | 'success' | 'failed';
}

export const pipeApi = {
  list: () => apiFetch<{ pipes: BotPipe[] }>('/admin/bot-pipes/'),

  create: (data: {
    name: string;
    source_bot_id: string;
    dest_bot_id: string;
    transform?: string;
    enabled?: boolean;
  }) =>
    apiFetch<{ message: string; pipe: BotPipe }>('/admin/bot-pipes/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (
    id: string,
    data: Partial<{
      name: string;
      source_bot_id: string;
      dest_bot_id: string;
      transform: string;
      enabled: boolean;
    }>,
  ) =>
    apiFetch<{ message: string; pipe: BotPipe }>(`/admin/bot-pipes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  listExecutions: () =>
    apiFetch<{ executions: BotPipeExecution[] }>('/admin/bot-pipes/executions'),
};
