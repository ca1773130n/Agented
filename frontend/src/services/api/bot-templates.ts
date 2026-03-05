/**
 * Bot Template API module.
 */
import { apiFetch } from './client';
import type { BotTemplate, BotTemplateDeployResponse } from './types';

export const botTemplateApi = {
  list: () => apiFetch<{ templates: BotTemplate[] }>('/admin/bot-templates'),

  get: (id: string) => apiFetch<BotTemplate>('/admin/bot-templates/' + id),

  deploy: (id: string) =>
    apiFetch<BotTemplateDeployResponse>('/admin/bot-templates/' + id + '/deploy', {
      method: 'POST',
    }),
};
