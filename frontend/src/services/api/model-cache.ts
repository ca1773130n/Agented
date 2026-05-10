/**
 * v0.7.8: Cached + auth-aware model discovery API client.
 *
 * Wraps three /admin/backends endpoints used by the operator console:
 *   GET  /admin/backends/{kind}/models[?auth_method=X]      — cached list (populates on miss).
 *   POST /admin/backends/{kind}/models/refresh[?auth_method=X] — force re-discovery.
 *   GET  /admin/backends/models/cache                       — operator overview.
 */
import { apiFetch } from './client';

export interface ModelCacheResponse {
  models: string[];
  backend_kind: string;
  auth_method: string;
  discovery_method: string;
  discovered_at: string;
  expires_at: string;
  error_message: string | null;
  fresh: boolean;
}

export interface ModelCacheEntry {
  id: number;
  backend_kind: string;
  auth_method: string;
  models_json: string;
  discovery_method: string;
  discovered_at: string;
  expires_at: string;
  error_message: string | null;
}

export const modelCacheApi = {
  list(backendKind: string, authMethod: string = 'unknown'): Promise<ModelCacheResponse> {
    return apiFetch<ModelCacheResponse>(
      `/admin/backends/${encodeURIComponent(backendKind)}/models?auth_method=${encodeURIComponent(authMethod)}`,
    );
  },
  refresh(backendKind: string, authMethod: string = 'unknown'): Promise<ModelCacheResponse> {
    return apiFetch<ModelCacheResponse>(
      `/admin/backends/${encodeURIComponent(backendKind)}/models/refresh?auth_method=${encodeURIComponent(authMethod)}`,
      { method: 'POST' },
    );
  },
  cacheOverview(): Promise<{ entries: ModelCacheEntry[] }> {
    return apiFetch<{ entries: ModelCacheEntry[] }>(`/admin/backends/models/cache`);
  },
};
