/**
 * Plugin, plugin export, and plugin conversation API modules.
 */
import { API_BASE, apiFetch } from './client';
import type {
  Plugin,
  PluginComponent,
  PluginConversation,
  PluginExportRequest,
  PluginExportResponse,
  PluginImportRequest,
  PluginImportResponse,
  PluginImportFromMarketplaceRequest,
  PluginDeployRequest,
  PluginDeployResponse,
  SyncStatus,
  PluginExportRecord,
} from './types';

// Plugin API
export const pluginApi = {
  list: (params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiFetch<{ plugins: Plugin[]; total_count?: number }>(`/admin/plugins${query ? `?${query}` : ''}`);
  },

  get: (pluginId: string) => apiFetch<Plugin>(`/admin/plugins/${pluginId}`),

  create: (data: {
    name: string;
    description?: string;
    version?: string;
    status?: string;
    author?: string;
  }) => apiFetch<{ message: string; plugin: Plugin }>('/admin/plugins', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (pluginId: string, data: Partial<{
    name: string;
    description: string;
    version: string;
    status: string;
    author: string;
  }>) => apiFetch<Plugin>(`/admin/plugins/${pluginId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (pluginId: string) => apiFetch<{ message: string }>(`/admin/plugins/${pluginId}`, {
    method: 'DELETE',
  }),

  // Component operations
  listComponents: (pluginId: string) => apiFetch<{ components: PluginComponent[] }>(`/admin/plugins/${pluginId}/components`),

  addComponent: (pluginId: string, data: {
    name: string;
    type: string;
    content?: string;
  }) => apiFetch<{ message: string; component: PluginComponent }>(`/admin/plugins/${pluginId}/components`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  updateComponent: (pluginId: string, componentId: number, data: Partial<{
    name: string;
    type: string;
    content: string;
  }>) => apiFetch<{ component: PluginComponent }>(`/admin/plugins/${pluginId}/components/${componentId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  removeComponent: (pluginId: string, componentId: number) =>
    apiFetch<{ message: string }>(`/admin/plugins/${pluginId}/components/${componentId}`, {
      method: 'DELETE',
    }),
};

// Plugin Export API
export const pluginExportApi = {
  export: (data: PluginExportRequest) =>
    apiFetch<PluginExportResponse>('/admin/plugin-exports/export', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  import: (data: PluginImportRequest) =>
    apiFetch<PluginImportResponse>('/admin/plugin-exports/import', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  importFromMarketplace: (data: PluginImportFromMarketplaceRequest) =>
    apiFetch<PluginImportResponse>('/admin/plugin-exports/import-from-marketplace', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deploy: (data: PluginDeployRequest) =>
    apiFetch<PluginDeployResponse>('/admin/plugin-exports/deploy', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  testConnection: (marketplaceId: string) =>
    apiFetch<{ connected: boolean; message: string }>('/admin/plugin-exports/test-connection', {
      method: 'POST',
      body: JSON.stringify({ marketplace_id: marketplaceId }),
    }),

  listExports: (pluginId: string) =>
    apiFetch<{ exports: PluginExportRecord[] }>(`/admin/plugin-exports/${pluginId}/exports`),

  sync: (pluginId: string, pluginDir: string) =>
    apiFetch<{ synced: number; skipped: number; errors: number }>('/admin/plugin-exports/sync', {
      method: 'POST',
      body: JSON.stringify({ plugin_id: pluginId, plugin_dir: pluginDir }),
    }),

  syncEntity: (entityType: string, entityId: string, pluginId: string, pluginDir: string) =>
    apiFetch<{ synced: boolean }>('/admin/plugin-exports/sync/entity', {
      method: 'POST',
      body: JSON.stringify({ entity_type: entityType, entity_id: entityId, plugin_id: pluginId, plugin_dir: pluginDir }),
    }),

  toggleWatch: (pluginId: string, pluginDir: string, enabled: boolean) =>
    apiFetch<{ watching: boolean; plugin_id: string }>('/admin/plugin-exports/watch', {
      method: 'POST',
      body: JSON.stringify({ plugin_id: pluginId, plugin_dir: pluginDir, enabled }),
    }),

  getSyncStatus: (pluginId: string) =>
    apiFetch<SyncStatus>(`/admin/plugin-exports/${pluginId}/sync-status`),
};

// Plugin Conversation API
export const pluginConversationApi = {
  start: () => apiFetch<{ conversation_id: string; message: string }>('/api/plugins/conversations/start', {
    method: 'POST',
  }),

  get: (convId: string) => apiFetch<PluginConversation>(`/api/plugins/conversations/${convId}`),

  sendMessage: (convId: string, message: string, options?: { backend?: string; account_id?: string; model?: string }) =>
    apiFetch<{ message_id: string; status: string }>(`/api/plugins/conversations/${convId}/message`, {
      method: 'POST',
      body: JSON.stringify({ message, ...options }),
    }),

  stream: (convId: string): EventSource => {
    return new EventSource(`${API_BASE}/api/plugins/conversations/${convId}/stream`);
  },

  finalize: (convId: string) =>
    apiFetch<{ message: string; plugin_id: string; plugin: Plugin }>(`/api/plugins/conversations/${convId}/finalize`, {
      method: 'POST',
    }),

  abandon: (convId: string) =>
    apiFetch<{ message: string }>(`/api/plugins/conversations/${convId}/abandon`, {
      method: 'POST',
    }),
};
