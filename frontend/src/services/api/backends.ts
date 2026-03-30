/**
 * AI Backends API module with login info and plan option constants.
 */
import { API_BASE, apiFetch } from './client';
import type {
  AIBackend,
  AIBackendWithAccounts,
  BackendCapabilities,
  RateLimitWindow,
} from './types';

export const BACKEND_LOGIN_INFO: Record<string, { url: string; label: string; description: string; loginCommand?: string }> = {
  claude: { url: 'https://console.anthropic.com', label: 'Anthropic Console', description: 'Manage your Claude account and billing', loginCommand: 'claude /login' },
  codex: { url: 'https://platform.openai.com', label: 'OpenAI Platform', description: 'Manage your OpenAI account and billing', loginCommand: 'codex login' },
  gemini: { url: 'https://aistudio.google.com', label: 'Google AI Studio', description: 'Manage your Gemini account and billing', loginCommand: 'gemini auth login' },
};

export const BACKEND_PLAN_OPTIONS: Record<string, { value: string; label: string }[]> = {
  claude: [
    { value: 'free', label: 'Free' },
    { value: 'pro', label: 'Pro ($20/mo)' },
    { value: 'max_5x', label: 'Max 5x ($100/mo)' },
    { value: 'max_20x', label: 'Max 20x ($200/mo)' },
    { value: 'team', label: 'Team' },
    { value: 'enterprise', label: 'Enterprise' },
  ],
  codex: [
    { value: 'free', label: 'Free' },
    { value: 'plus', label: 'Plus ($20/mo)' },
    { value: 'pro', label: 'Pro ($200/mo)' },
    { value: 'team', label: 'Team' },
    { value: 'enterprise', label: 'Enterprise' },
  ],
  gemini: [
    { value: 'free', label: 'Free' },
    { value: 'pro', label: 'Pro' },
    { value: 'ultra', label: 'Ultra' },
  ],
  // opencode has no plans — it's a free open-source tool
};

// AI Backends API
export const backendApi = {
  list: () => apiFetch<{ backends: AIBackend[] }>('/admin/backends'),

  get: (backendId: string) => apiFetch<AIBackendWithAccounts>(`/admin/backends/${backendId}`),

  installCli: (backendId: string) => apiFetch<{
    message: string;
    version?: string;
    error?: string;
  }>(`/admin/backends/${backendId}/install`, {
    method: 'POST',
  }),

  check: (backendId: string) => apiFetch<{
    installed: boolean;
    version?: string;
    cli_path?: string;
    capabilities?: BackendCapabilities;
  }>(`/admin/backends/${backendId}/check`, {
    method: 'POST',
  }),

  // Account management
  addAccount: (backendId: string, data: {
    account_name: string;
    email?: string;
    config_path?: string;
    api_key_env?: string;
    is_default?: number;
    plan?: string;
  }) => apiFetch<{ message: string; account_id: number }>(`/admin/backends/${backendId}/accounts`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  updateAccount: (backendId: string, accountId: number, data: Partial<{
    account_name: string;
    email: string;
    config_path: string;
    api_key_env: string;
    is_default: number;
    plan: string;
  }>) => apiFetch<{ message: string }>(`/admin/backends/${backendId}/accounts/${accountId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  deleteAccount: (backendId: string, accountId: number) =>
    apiFetch<{ message: string }>(`/admin/backends/${backendId}/accounts/${accountId}`, {
      method: 'DELETE',
    }),

  // Connect (OAuth login) operations
  startConnect: (backendId: string, configPath?: string, email?: string, accountName?: string) =>
    apiFetch<{ session_id: string; status: string }>(`/admin/backends/${backendId}/connect`, {
      method: 'POST',
      body: JSON.stringify({
        ...(configPath ? { config_path: configPath } : {}),
        ...(email ? { email } : {}),
        ...(accountName ? { account_name: accountName } : {}),
      }),
    }),

  streamConnectUrl: (backendId: string, sessionId: string): string =>
    `${API_BASE}/admin/backends/${backendId}/connect/${sessionId}/stream`,

  respondConnect: (backendId: string, sessionId: string, interactionId: string, response: Record<string, unknown>) =>
    apiFetch<{ status: string }>(`/admin/backends/${backendId}/connect/${sessionId}/respond`, {
      method: 'POST',
      body: JSON.stringify({ interaction_id: interactionId, response }),
    }),

  cancelConnect: (backendId: string, sessionId: string) =>
    apiFetch<{ message: string }>(`/admin/backends/${backendId}/connect/${sessionId}`, {
      method: 'DELETE',
    }),

  // Usage check (CLI-based)
  checkUsage: (backendId: string, accountId: number) =>
    apiFetch<{ success: boolean; output?: string; error?: string }>(`/admin/backends/${backendId}/accounts/${accountId}/usage`, {
      method: 'POST',
    }),

  // Rate limit check (provider API-based)
  checkRateLimits: (backendId: string, accountId: number) =>
    apiFetch<{ windows: RateLimitWindow[]; message?: string; needs_login?: boolean; account_id?: number }>(`/admin/backends/${backendId}/accounts/${accountId}/rate-limits`, {
      method: 'POST',
    }),

  // Auth status check (credential-based, no subprocess)
  checkAuthStatus: (backendId: string) =>
    apiFetch<{
      backend_type: string;
      accounts: Array<{ account_id: number; name: string; email: string; authenticated: boolean }>;
      login_instruction: string;
    }>(`/admin/backends/${backendId}/auth-status`),

  // Model discovery (CLI-based introspection)
  discoverModels: (backendId: string) =>
    apiFetch<{ models: string[]; backend_id: string }>(`/admin/backends/${backendId}/discover-models`, {
      method: 'POST',
    }),

  // CLIProxyAPI account management
  proxyLogin: (backendType?: string, configPath?: string) =>
    apiFetch<{ status: string; message: string; oauth_url?: string; device_code?: string; output?: string[] }>('/admin/backends/proxy/login', {
      method: 'POST',
      body: JSON.stringify({
        ...(backendType && { backend_type: backendType }),
        ...(configPath && { config_path: configPath }),
      }),
    }),

  // Gemini direct OAuth (bypasses CLI TUI)
  geminiAuthStart: (configPath?: string, email?: string) =>
    apiFetch<{ status: string; oauth_url: string; state: string }>('/admin/backends/gemini/auth-start', {
      method: 'POST',
      body: JSON.stringify({ config_path: configPath, email }),
    }),

  geminiAuthComplete: (code: string, state: string) =>
    apiFetch<{ status: string; message: string }>('/admin/backends/gemini/auth-complete', {
      method: 'POST',
      body: JSON.stringify({ code, state }),
    }),

  proxyCallbackForward: (callbackUrl: string) =>
    apiFetch<{ status: string; message: string }>('/admin/backends/proxy/callback-forward', {
      method: 'POST',
      body: JSON.stringify({ callback_url: callbackUrl }),
    }),

  proxyStatus: () =>
    apiFetch<{ available: boolean; account_count: number; accounts: Array<{ email: string; type: string; disabled: boolean; expired: string }> }>('/admin/backends/proxy/status'),

  listProxyAccounts: () =>
    apiFetch<{ accounts: Array<{ email: string; type: string; disabled: boolean; expired: string }> }>('/admin/backends/proxy/accounts'),

  // One-shot prompt testing
  testPrompt: (backendType: string, prompt: string, accountId?: string, model?: string) =>
    apiFetch<{ test_id: string; status: string }>('/admin/backends/test', {
      method: 'POST',
      body: JSON.stringify({ backend_type: backendType, prompt, account_id: accountId, model }),
    }),

  streamTestUrl: (testId: string): string =>
    `${API_BASE}/admin/backends/test/${testId}/stream`,
};
