/**
 * Repo-bot-defaults API module.
 * Provides a per-repository view of which bots are bound to each GitHub repo.
 */
import { apiFetch } from './client';

export interface RepoBotBinding {
  repo: string;
  bots: string[];
  projectCount: number;
  enabled: boolean;
}

export interface AvailableBot {
  id: string;
  name: string;
  type: 'security' | 'review' | 'test' | 'docs';
}

export interface RepoBotDefaultsListResponse {
  bindings: RepoBotBinding[];
  bots: AvailableBot[];
}

export interface CreateRepoBotDefaultRequest {
  repo: string;
  bot_ids: string[];
}

export interface CreateRepoBotDefaultResponse {
  repo: string;
  bound_bots: string[];
  errors: string[];
}

export interface ToggleRepoBotDefaultResponse {
  repo: string;
  enabled: boolean;
  updated_triggers: string[];
}

export interface DeleteRepoBotDefaultResponse {
  repo: string;
  removed_triggers: string[];
}

/** Encode owner/repo as URL-safe slug. */
function repoToSlug(repo: string): string {
  return repo.replace('/', '__');
}

export const repoBotDefaultsApi = {
  /** List all repo-bot bindings. */
  list: () =>
    apiFetch<RepoBotDefaultsListResponse>('/admin/repo-bot-defaults/'),

  /** Bind bots to a repository. */
  create: (body: CreateRepoBotDefaultRequest) =>
    apiFetch<CreateRepoBotDefaultResponse>('/admin/repo-bot-defaults/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  /** Enable or disable all bindings for a repository. */
  toggleEnabled: (repo: string, enabled: boolean) =>
    apiFetch<ToggleRepoBotDefaultResponse>(
      `/admin/repo-bot-defaults/${repoToSlug(repo)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      }
    ),

  /** Remove all bindings for a repository. */
  remove: (repo: string) =>
    apiFetch<DeleteRepoBotDefaultResponse>(
      `/admin/repo-bot-defaults/${repoToSlug(repo)}`,
      { method: 'DELETE' }
    ),
};
