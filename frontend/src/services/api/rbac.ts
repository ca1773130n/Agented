/**
 * RBAC (Role-Based Access Control) API module.
 */
import { apiFetch } from './client';

export interface UserRole {
  id: string;
  api_key: string;
  label: string;
  role: string;
  created_at: string | null;
  updated_at: string | null;
}

export type PermissionMatrix = Record<string, string[]>;

export const rbacApi = {
  listRoles: () =>
    apiFetch<{ roles: UserRole[] }>('/admin/rbac/roles'),

  getRole: (roleId: string) =>
    apiFetch<UserRole>(`/admin/rbac/roles/${roleId}`),

  createRole: (data: { api_key: string; label: string; role: string }) =>
    apiFetch<{ message: string; role: UserRole }>('/admin/rbac/roles', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateRole: (roleId: string, data: { label?: string; role?: string }) =>
    apiFetch<UserRole>(`/admin/rbac/roles/${roleId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteRole: (roleId: string) =>
    apiFetch<{ message: string }>(`/admin/rbac/roles/${roleId}`, {
      method: 'DELETE',
    }),

  getPermissions: () =>
    apiFetch<{ permissions: PermissionMatrix }>('/admin/rbac/permissions'),
};
