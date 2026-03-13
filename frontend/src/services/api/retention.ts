/**
 * Retention policy API module.
 */
import { apiFetch } from './client';

export interface RetentionPolicy {
  id: string;
  category: string;
  scope: string;
  scope_name: string;
  retention_days: number;
  delete_on_expiry: number;
  archive_on_expiry: number;
  estimated_size_gb: number;
  enabled: number;
  created_at?: string;
}

export interface CreateRetentionPolicyRequest {
  category: string;
  scope?: string;
  scope_name?: string;
  retention_days?: number;
  delete_on_expiry?: boolean;
  archive_on_expiry?: boolean;
  estimated_size_gb?: number;
}

export const retentionApi = {
  list: (): Promise<{ policies: RetentionPolicy[] }> =>
    apiFetch<{ policies: RetentionPolicy[] }>('/admin/retention-policies/'),

  create: (data: CreateRetentionPolicyRequest): Promise<RetentionPolicy> =>
    apiFetch<RetentionPolicy>('/admin/retention-policies/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  toggle: (policyId: string, enabled: boolean): Promise<{ id: string; enabled: boolean }> =>
    apiFetch<{ id: string; enabled: boolean }>(
      `/admin/retention-policies/${policyId}/toggle`,
      {
        method: 'PATCH',
        body: JSON.stringify({ enabled }),
      }
    ),

  delete: (policyId: string): Promise<void> =>
    apiFetch<void>(`/admin/retention-policies/${policyId}`, {
      method: 'DELETE',
    }),

  runCleanup: (): Promise<{ message: string }> =>
    apiFetch<{ message: string }>('/admin/retention-policies/cleanup', {
      method: 'POST',
    }),
};
