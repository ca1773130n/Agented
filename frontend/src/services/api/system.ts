/**
 * System API modules: health, version, utility, settings, and setup.
 */
import { API_BASE, apiFetch } from './client';
import type {
  HealthStatus,
  BackendCheck,
  PathValidation,
  GitHubValidation,
  SkillInfo,
  HarnessPluginSettings,
  SetupExecution,
  BundleInstallResponse,
} from './types';

// Health API
export const healthApi = {
  liveness: () => fetch(`${API_BASE}/health/liveness`).then(r => r.ok),
  readiness: () => apiFetch<HealthStatus>(`/health/readiness`),
};

// Version API
export const versionApi = {
  get: () => apiFetch<{ version: string }>('/api/version'),
};

// Utility API
export const utilityApi = {
  checkBackend: (name: 'claude' | 'opencode') =>
    apiFetch<BackendCheck>(`/api/check-backend?name=${name}`),

  validatePath: (path: string) =>
    apiFetch<PathValidation>(`/api/validate-path?path=${encodeURIComponent(path)}`),

  validateGitHubUrl: (url: string) =>
    apiFetch<GitHubValidation>(`/api/validate-github-url?url=${encodeURIComponent(url)}`),

  discoverSkills: (triggerId?: string) => {
    const params = new URLSearchParams();
    if (triggerId) params.set('trigger_id', triggerId);
    const query = params.toString();
    return apiFetch<{ skills: SkillInfo[] }>(`/api/discover-skills${query ? `?${query}` : ''}`);
  },
};

// Settings API
export const settingsApi = {
  getAll: () => apiFetch<{ settings: Record<string, string> }>('/api/settings'),

  get: (key: string) => apiFetch<{ key: string; value: string }>(`/api/settings/${key}`),

  set: (key: string, value: string) => apiFetch<{ key: string; value: string }>(`/api/settings/${key}`, {
    method: 'PUT',
    body: JSON.stringify({ value }),
  }),

  delete: (key: string) => apiFetch<{ message: string }>(`/api/settings/${key}`, {
    method: 'DELETE',
  }),

  // Harness plugin specific
  getHarnessPlugin: () => apiFetch<HarnessPluginSettings>('/api/settings/harness-plugin'),

  setHarnessPlugin: (data: HarnessPluginSettings) =>
    apiFetch<HarnessPluginSettings>('/api/settings/harness-plugin', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
};

// Setup API
export const setupApi = {
  async start(projectId: string, command: string): Promise<{ execution_id: string; status: string }> {
    return apiFetch('/api/setup/start', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, command }),
    });
  },

  async respond(executionId: string, interactionId: string, response: Record<string, unknown>): Promise<{ status: string }> {
    return apiFetch(`/api/setup/${executionId}/respond`, {
      method: 'POST',
      body: JSON.stringify({ interaction_id: interactionId, response }),
    });
  },

  async getStatus(executionId: string): Promise<SetupExecution> {
    return apiFetch(`/api/setup/${executionId}/status`);
  },

  async cancel(executionId: string): Promise<{ message: string }> {
    return apiFetch(`/api/setup/${executionId}`, { method: 'DELETE' });
  },

  streamUrl(executionId: string): string {
    return `/api/setup/${executionId}/stream`;
  },

  async bundleInstall(): Promise<BundleInstallResponse> {
    return apiFetch('/api/setup/bundle-install', { method: 'POST' });
  },
};
