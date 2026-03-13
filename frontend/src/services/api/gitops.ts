/**
 * GitOps repository sync API module.
 */
import { apiFetch } from './client';

export interface GitOpsRepo {
  id: string;
  name: string;
  repo_url: string;
  branch: string;
  config_path: string;
  poll_interval_seconds: number;
  enabled: number | boolean;
  last_sync_sha: string | null;
  last_sync_at: string | null;
  last_sync_status: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface SyncLog {
  id: string;
  repo_id: string;
  status: string;
  changes_summary: string | null;
  error_message: string | null;
  dry_run: number | boolean;
  created_at: string;
}

export interface SyncResult {
  status: string;
  changes?: unknown[];
  error?: string;
}

export const gitopsApi = {
  listRepos: () =>
    apiFetch<GitOpsRepo[]>('/admin/gitops/repos'),

  getRepo: (repoId: string) =>
    apiFetch<GitOpsRepo>(`/admin/gitops/repos/${repoId}`),

  createRepo: (data: {
    name: string;
    repo_url: string;
    branch?: string;
    config_path?: string;
    poll_interval_seconds?: number;
  }) =>
    apiFetch<GitOpsRepo>('/admin/gitops/repos', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateRepo: (repoId: string, data: {
    name?: string;
    repo_url?: string;
    branch?: string;
    config_path?: string;
    poll_interval_seconds?: number;
    enabled?: boolean;
  }) =>
    apiFetch<GitOpsRepo>(`/admin/gitops/repos/${repoId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteRepo: (repoId: string) =>
    apiFetch<{ message: string }>(`/admin/gitops/repos/${repoId}`, {
      method: 'DELETE',
    }),

  triggerSync: (repoId: string, dryRun = false) =>
    apiFetch<SyncResult>(`/admin/gitops/repos/${repoId}/sync${dryRun ? '?dry_run=true' : ''}`, {
      method: 'POST',
    }),

  getSyncLogs: (repoId: string, limit = 20) =>
    apiFetch<SyncLog[]>(`/admin/gitops/repos/${repoId}/logs?limit=${limit}`),
};
