/**
 * Marketplace API module.
 */
import { apiFetch } from './client';
import type {
  Marketplace,
  MarketplacePlugin,
  MarketplaceSearchResponse,
} from './types';

// Marketplace API
export const marketplaceApi = {
  list: () => apiFetch<{ marketplaces: Marketplace[] }>('/admin/marketplaces'),

  get: (marketplaceId: string) => apiFetch<Marketplace>(`/admin/marketplaces/${marketplaceId}`),

  create: (data: {
    name: string;
    url: string;
    type?: string;
    is_default?: boolean;
  }) => apiFetch<{ message: string; marketplace: Marketplace }>('/admin/marketplaces', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (marketplaceId: string, data: Partial<{
    name: string;
    url: string;
    type: string;
    is_default: boolean;
  }>) => apiFetch<Marketplace>(`/admin/marketplaces/${marketplaceId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (marketplaceId: string) => apiFetch<{ message: string }>(`/admin/marketplaces/${marketplaceId}`, {
    method: 'DELETE',
  }),

  // Plugin operations
  listPlugins: (marketplaceId: string) => apiFetch<{ plugins: MarketplacePlugin[] }>(`/admin/marketplaces/${marketplaceId}/plugins`),

  installPlugin: (marketplaceId: string, data: {
    remote_name: string;
    version?: string;
    plugin_id?: string;
  }) => apiFetch<{ message: string; plugin: MarketplacePlugin }>(`/admin/marketplaces/${marketplaceId}/plugins`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  uninstallPlugin: (marketplaceId: string, pluginId: string) =>
    apiFetch<{ message: string }>(`/admin/marketplaces/${marketplaceId}/plugins/${pluginId}`, {
      method: 'DELETE',
    }),

  discoverPlugins: (marketplaceId: string) =>
    apiFetch<{ plugins: Array<{ name: string; description?: string; version?: string; source?: string; installed: boolean }>; total: number }>(
      `/admin/marketplaces/${marketplaceId}/plugins/available`
    ),

  search: (query: string, type: 'plugin' | 'skill' = 'plugin') =>
    apiFetch<MarketplaceSearchResponse>(`/admin/marketplaces/search?q=${encodeURIComponent(query)}&type=${type}`),

  refreshCache: () =>
    apiFetch<{ message: string }>('/admin/marketplaces/search/refresh', { method: 'POST' }),
};
