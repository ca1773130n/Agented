/**
 * Secrets vault API module.
 */
import { apiFetch } from './client';

export interface SecretMetadata {
  id: string;
  name: string;
  description: string;
  scope: string;
  created_by: string;
  created_at: string;
  updated_at: string | null;
  last_accessed_at: string | null;
}

export interface VaultStatus {
  configured: boolean;
  secret_count: number;
}

export interface RevealedSecret {
  id: string;
  name: string;
  value: string;
}

export const secretsApi = {
  getStatus: () =>
    apiFetch<VaultStatus>('/admin/secrets/status'),

  list: () =>
    apiFetch<{ secrets: SecretMetadata[] }>('/admin/secrets'),

  get: (secretId: string) =>
    apiFetch<SecretMetadata>(`/admin/secrets/${secretId}`),

  create: (data: { name: string; value: string; description?: string; scope?: string }) =>
    apiFetch<SecretMetadata>('/admin/secrets', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (secretId: string, data: { value?: string; description?: string }) =>
    apiFetch<SecretMetadata>(`/admin/secrets/${secretId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (secretId: string) =>
    apiFetch<{ message: string }>(`/admin/secrets/${secretId}`, {
      method: 'DELETE',
    }),

  reveal: (secretId: string) =>
    apiFetch<RevealedSecret>(`/admin/secrets/${secretId}/reveal`, {
      method: 'POST',
    }),
};
