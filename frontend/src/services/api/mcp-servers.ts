/**
 * MCP server configuration management API module.
 */
import { apiFetch } from './client';
import type { McpServer, ProjectMcpServerDetail, McpSyncResult } from './types';

export const mcpServerApi = {
  // CRUD
  list: (params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiFetch<{ servers: McpServer[]; total_count?: number }>(`/admin/mcp-servers/${query ? `?${query}` : ''}`);
  },

  get: (id: string) => apiFetch<McpServer>(`/admin/mcp-servers/${id}`),

  create: (data: Partial<McpServer>) =>
    apiFetch<{ id: string }>('/admin/mcp-servers/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: Partial<McpServer>) =>
    apiFetch<McpServer>(`/admin/mcp-servers/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiFetch<{ message: string }>(`/admin/mcp-servers/${id}`, {
      method: 'DELETE',
    }),

  // Project MCP assignment
  listForProject: (projectId: string) =>
    apiFetch<{ servers: ProjectMcpServerDetail[] }>(
      `/admin/projects/${projectId}/mcp-servers`
    ),

  assignToProject: (projectId: string, serverId: string, envOverrides?: string) =>
    apiFetch<{ message: string }>(
      `/admin/projects/${projectId}/mcp-servers/${serverId}`,
      {
        method: 'POST',
        body: JSON.stringify(
          envOverrides ? { env_overrides_json: envOverrides } : {}
        ),
      }
    ),

  updateAssignment: (
    projectId: string,
    serverId: string,
    data: { enabled?: number; env_overrides_json?: string }
  ) =>
    apiFetch<{ message: string }>(
      `/admin/projects/${projectId}/mcp-servers/${serverId}`,
      {
        method: 'PUT',
        body: JSON.stringify(data),
      }
    ),

  unassignFromProject: (projectId: string, serverId: string) =>
    apiFetch<{ message: string }>(
      `/admin/projects/${projectId}/mcp-servers/${serverId}`,
      {
        method: 'DELETE',
      }
    ),

  // Sync
  syncProject: (projectId: string) =>
    apiFetch<McpSyncResult>(`/admin/mcp-servers/sync/${projectId}`, {
      method: 'POST',
    }),

  previewSync: (projectId: string) =>
    apiFetch<McpSyncResult>(`/admin/mcp-servers/sync/${projectId}/preview`),

  testConnection: (id: string) =>
    apiFetch<{ success: boolean; message: string }>(`/admin/mcp-servers/${id}/test`),
};
