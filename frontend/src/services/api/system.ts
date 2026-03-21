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

  /** Check whether the backend requires API key authentication. Public endpoint. */
  authStatus: () =>
    apiFetch<{ auth_required: boolean; authenticated: boolean; needs_setup?: boolean }>('/health/auth-status'),

  /** Verify an API key without storing it. Public endpoint. */
  verifyKey: (apiKey: string) =>
    apiFetch<{ valid: boolean; message: string }>('/health/verify-key', {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey }),
    }),

  /** First-run setup: generate the initial admin API key. Public endpoint. */
  setup: (label?: string) =>
    apiFetch<{ api_key: string; role_id: string; role: string; label: string; message: string }>(
      '/health/setup',
      {
        method: 'POST',
        body: JSON.stringify({ label: label || 'Admin' }),
      }
    ),
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
// System Error API
import type {
  SystemErrorWithFixes,
  SystemErrorListResponse,
  ErrorCountsResponse,
  ReportErrorRequest,
} from './types/system';

export const systemErrorApi = {
  listErrors: (params?: Record<string, string | number>) => {
    const query = params ? '?' + new URLSearchParams(
      Object.entries(params).reduce((acc, [k, v]) => { if (v != null) acc[k] = String(v); return acc; }, {} as Record<string, string>)
    ).toString() : '';
    return apiFetch<SystemErrorListResponse>(`/admin/system/errors${query}`);
  },

  getError: (id: string) =>
    apiFetch<SystemErrorWithFixes>(`/admin/system/errors/${id}`),

  reportError: (data: ReportErrorRequest) =>
    apiFetch<{ error_id: string }>('/admin/system/errors', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateError: (id: string, data: { status: string }) =>
    apiFetch<{ message: string }>(`/admin/system/errors/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  retryFix: (id: string) =>
    apiFetch<{ message: string }>(`/admin/system/errors/${id}/retry-fix`, {
      method: 'POST',
    }),

  getLogs: (lines?: number) =>
    apiFetch<{ lines: string[] }>(`/admin/system/logs${lines ? `?lines=${lines}` : ''}`),

  getCounts: () =>
    apiFetch<ErrorCountsResponse>('/admin/system/errors/counts'),
};

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
