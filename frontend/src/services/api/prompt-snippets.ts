/**
 * Prompt Snippet API module.
 */
import { apiFetch } from './client';
import type {
  PromptSnippet,
  CreateSnippetRequest,
  UpdateSnippetRequest,
} from './types';

export const promptSnippetApi = {
  list: () => apiFetch<{ snippets: PromptSnippet[] }>('/admin/prompt-snippets'),

  get: (id: string) => apiFetch<PromptSnippet>('/admin/prompt-snippets/' + id),

  create: (data: CreateSnippetRequest) =>
    apiFetch<PromptSnippet>('/admin/prompt-snippets', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: UpdateSnippetRequest) =>
    apiFetch<PromptSnippet>('/admin/prompt-snippets/' + id, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiFetch<void>('/admin/prompt-snippets/' + id, { method: 'DELETE' }),

  resolve: (text: string) =>
    apiFetch<{ resolved: string }>('/admin/prompt-snippets/resolve', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
};
