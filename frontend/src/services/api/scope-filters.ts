/**
 * API client for repository scope filters (per-trigger allowlist / denylist patterns).
 */

import { apiFetch } from './client';

export interface ScopeFilter {
  id: string;
  trigger_id: string;
  trigger_name: string | null;
  mode: 'allowlist' | 'denylist';
  enabled: boolean;
  updated_at: string;
  patterns?: ScopeFilterPattern[];
}

export interface ScopeFilterPattern {
  id: string;
  filter_id: string;
  type: 'repo' | 'branch' | 'author';
  pattern: string;
  description: string;
  created_at: string;
}

export interface ListScopeFiltersResponse {
  filters: ScopeFilter[];
  total: number;
}

export interface UpsertScopeFilterRequest {
  trigger_id: string;
  mode?: 'allowlist' | 'denylist';
  enabled?: boolean;
}

export interface UpdateScopeFilterRequest {
  mode?: 'allowlist' | 'denylist';
  enabled?: boolean;
}

export interface AddPatternRequest {
  type: 'repo' | 'branch' | 'author';
  pattern: string;
  description?: string;
}

export const scopeFiltersApi = {
  /** List all scope filters (with trigger name). */
  list: () => apiFetch<ListScopeFiltersResponse>('/admin/scope-filters'),

  /** Get a single scope filter with its patterns. */
  get: (filterId: string) => apiFetch<ScopeFilter>(`/admin/scope-filters/${filterId}`),

  /** Create or update a scope filter for a trigger. */
  upsert: (body: UpsertScopeFilterRequest) =>
    apiFetch<{ message: string; filter: ScopeFilter }>('/admin/scope-filters', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  /** Update mode and/or enabled state of a scope filter. */
  update: (filterId: string, body: UpdateScopeFilterRequest) =>
    apiFetch<ScopeFilter>(`/admin/scope-filters/${filterId}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  /** Add a pattern to a scope filter. */
  addPattern: (filterId: string, body: AddPatternRequest) =>
    apiFetch<{ message: string; pattern: ScopeFilterPattern }>(
      `/admin/scope-filters/${filterId}/patterns`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    ),

  /** Delete a pattern from a scope filter. */
  deletePattern: (filterId: string, patternId: string) =>
    apiFetch<{ message: string }>(
      `/admin/scope-filters/${filterId}/patterns/${patternId}`,
      { method: 'DELETE' }
    ),
};
