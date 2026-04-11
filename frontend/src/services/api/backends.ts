/**
 * AI Backends API module.
 *
 * CRUD operations (list, get, create, delete) are now served by the
 * @ai-accounts/ts-core AiAccountsClient via /api/v1/backends.
 *
 * Agented-specific management operations (install CLI, connect sessions,
 * rate-limit checks, proxy login, Gemini auth, etc.) are served by the
 * Flask admin API at /admin/backends and remain here as `backendManagementApi`.
 */
import { API_BASE, apiFetch } from './client';
import { AiAccountsClient } from '@ai-accounts/ts-core';
import type {
  AIBackend,
  AIBackendWithAccounts,
  BackendAccount,
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

/**
 * Shared AiAccountsClient singleton for the Litestar /api/v1/backends API.
 * Replaces the old backendApi CRUD methods (list, get, create, delete).
 */
export const aiAccountsClient = new AiAccountsClient({ baseUrl: '' });

/**
 * Agented-specific backend management operations that are NOT part of the
 * @ai-accounts/litestar CRUD surface. These call Flask /admin/backends/* routes
 * for CLI install, OAuth connect sessions, rate-limit checks, proxy auth, etc.
 */
export const backendManagementApi = {
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
  checkUsage: (backendId: string, accountId: string | number) =>
    apiFetch<{ success: boolean; output?: string; error?: string }>(`/admin/backends/${backendId}/accounts/${accountId}/usage`, {
      method: 'POST',
    }),

  // Rate limit check (provider API-based)
  checkRateLimits: (backendId: string, accountId: string | number) =>
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

/**
 * Per-kind static metadata. Agented's UI displays one "backend" per kind
 * (claude, codex, gemini, opencode) with a list of "accounts" under it.
 * ai-accounts v0.2 is flat — each row is one account with a `kind` field.
 * The shim groups ai-accounts rows by kind and synthesizes one AIBackend
 * per kind with this metadata attached.
 */
const BACKEND_METADATA: Record<string, {
  name: string;
  description: string;
  icon?: string;
  documentation_url: string;
}> = {
  claude: {
    name: 'Claude',
    description: 'Anthropic Claude via the claude CLI',
    documentation_url: 'https://docs.anthropic.com/en/docs/claude-code/overview',
  },
  codex: {
    name: 'Codex',
    description: 'OpenAI Codex via the codex CLI',
    documentation_url: 'https://platform.openai.com/docs',
  },
  gemini: {
    name: 'Gemini',
    description: 'Google Gemini via the gemini CLI',
    documentation_url: 'https://ai.google.dev/gemini-api/docs',
  },
  opencode: {
    name: 'OpenCode',
    description: 'OpenCode open-source routing layer',
    documentation_url: 'https://opencode.ai',
  },
};

const KNOWN_KINDS: ReadonlyArray<string> = Object.keys(BACKEND_METADATA);

/** Convert an Agented legacy backend-id (`backend-claude`) or a kind slug to a kind. */
function legacyIdToKind(legacyIdOrKind: string): string {
  return legacyIdOrKind.startsWith('backend-')
    ? legacyIdOrKind.slice('backend-'.length)
    : legacyIdOrKind;
}

/** Convert a kind to Agented's legacy backend-id. */
function kindToLegacyId(kind: string): string {
  return `backend-${kind}`;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function dtoToAccount(dto: any): BackendAccount {
  const config = (dto?.config as Record<string, unknown>) ?? {};
  const pick = (key: string): string | undefined => {
    const v = config[key];
    return typeof v === 'string' ? v : undefined;
  };
  return {
    id: dto.id,
    backend_id: kindToLegacyId(dto.kind ?? ''),
    account_name: dto.display_name ?? dto.id,
    email: pick('email'),
    config_path: pick('config_path'),
    api_key_env: pick('api_key_env'),
    is_default: config.is_default === true ? 1 : 0,
    plan: pick('plan'),
    usage_data: (config.usage_data as Record<string, unknown>) ?? {},
  };
}

/** Enrich an AIBackend with detection data from Agented's legacy /admin/backends/<id>/check route. */
async function tryCheck(legacyId: string): Promise<{
  is_installed: number;
  version?: string;
  cli_path?: string;
  capabilities?: BackendCapabilities;
}> {
  try {
    const result = await backendManagementApi.check(legacyId);
    return {
      is_installed: result.installed ? 1 : 0,
      version: result.version,
      cli_path: result.cli_path,
      capabilities: result.capabilities,
    };
  } catch {
    return { is_installed: 0 };
  }
}

function buildBackendForKind(
  kind: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  dtos: any[],
  detection: {
    is_installed: number;
    version?: string;
    cli_path?: string;
    capabilities?: BackendCapabilities;
  },
): AIBackend {
  const meta = BACKEND_METADATA[kind] ?? {
    name: kind,
    description: '',
    documentation_url: '',
  };
  return {
    id: kindToLegacyId(kind),
    name: meta.name,
    type: kind,
    description: meta.description,
    documentation_url: meta.documentation_url,
    is_installed: detection.is_installed,
    version: detection.version,
    cli_path: detection.cli_path,
    capabilities: detection.capabilities,
    models: [],
    account_count: dtos.length,
  };
}

/**
 * backendApi — legacy CRUD shim backed by AiAccountsClient.
 *
 * Groups ai-accounts rows (flat `bkd-*` entities) into Agented's legacy
 * "one backend per kind with N accounts" shape. Static per-kind metadata
 * comes from BACKEND_METADATA; dynamic detection data comes from Agented's
 * surviving `/admin/backends/<legacyId>/check` route.
 *
 * Account CRUD operations (create, edit) are no longer exposed through
 * this shim — new accounts are added via `<AccountWizard>` /
 * `<OnboardingFlow>` which call aiAccountsClient directly. Deletes go
 * through `aiAccountsClient.deleteBackend(bkdId)`.
 */
export const backendApi = {
  list: async (): Promise<{ backends: AIBackend[] }> => {
    const { items } = await aiAccountsClient.listBackends();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const byKind: Record<string, any[]> = {};
    for (const dto of items) {
      const kind = (dto as { kind: string }).kind ?? '';
      if (!byKind[kind]) byKind[kind] = [];
      byKind[kind].push(dto);
    }
    const kinds = Array.from(new Set([...KNOWN_KINDS, ...Object.keys(byKind)]));
    const detections = await Promise.all(kinds.map((k) => tryCheck(kindToLegacyId(k))));
    const backends = kinds.map((kind, idx) =>
      buildBackendForKind(kind, byKind[kind] ?? [], detections[idx] ?? { is_installed: 0 }),
    );
    return { backends };
  },

  get: async (legacyIdOrKind: string): Promise<AIBackendWithAccounts> => {
    const kind = legacyIdToKind(legacyIdOrKind);
    const { items } = await aiAccountsClient.listBackends();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const kindDtos = items.filter((dto: any) => dto.kind === kind);
    const detection = await tryCheck(kindToLegacyId(kind));
    const base = buildBackendForKind(kind, kindDtos, detection);
    // Try to enrich with models (best-effort)
    let models: string[] = [];
    try {
      const result = await backendManagementApi.discoverModels(kindToLegacyId(kind));
      models = result.models ?? [];
    } catch {
      // Model discovery is optional
    }
    return {
      ...base,
      models,
      accounts: kindDtos.map(dtoToAccount),
    };
  },

  /**
   * Create a new account under a backend kind.
   *
   * The original Agented flow persisted an account row after the wizard's
   * CLI-based login completed via the /admin/backends/<kind>/connect SSE
   * stream. In the ai-accounts world we just create a Backend row pointing
   * at the user-chosen config_path; the actual credential state lives in
   * that isolation dir (owned by the CLI itself) or in the env var named
   * by api_key_env.
   */
  addAccount: async (
    legacyBackendId: string,
    data: {
      account_name: string;
      email?: string;
      config_path?: string;
      api_key_env?: string;
      plan?: string;
      is_default?: number;
      usage_data?: Record<string, unknown>;
    },
  ): Promise<{ id: string; message: string }> => {
    const kind = legacyIdToKind(legacyBackendId);
    const config: Record<string, unknown> = {};
    if (data.email) config.email = data.email;
    if (data.config_path) config.config_path = data.config_path;
    if (data.api_key_env) config.api_key_env = data.api_key_env;
    if (data.plan) config.plan = data.plan;
    config.is_default = data.is_default === 1;
    if (data.usage_data && Object.keys(data.usage_data).length > 0) {
      config.usage_data = data.usage_data;
    }
    const created = await aiAccountsClient.createBackend({
      kind,
      display_name: data.account_name,
      config,
    });
    return { id: created.id, message: 'Account created' };
  },

  /**
   * Update an existing account's display name and config.
   * accountId is the ai-accounts bkd-* id.
   */
  updateAccount: async (
    _legacyBackendId: string,
    accountId: string,
    data: {
      account_name?: string;
      email?: string;
      config_path?: string;
      api_key_env?: string;
      plan?: string;
      is_default?: number;
      usage_data?: Record<string, unknown>;
    },
  ): Promise<{ message: string }> => {
    const patch: { display_name?: string; config?: Record<string, unknown> } = {};
    if (data.account_name !== undefined) patch.display_name = data.account_name;
    const config: Record<string, unknown> = {};
    if (data.email !== undefined) config.email = data.email;
    if (data.config_path !== undefined) config.config_path = data.config_path;
    if (data.api_key_env !== undefined) config.api_key_env = data.api_key_env;
    if (data.plan !== undefined) config.plan = data.plan;
    if (data.is_default !== undefined) config.is_default = data.is_default === 1;
    if (data.usage_data !== undefined) config.usage_data = data.usage_data;
    if (Object.keys(config).length > 0) patch.config = config;
    await aiAccountsClient.updateBackend(accountId, patch);
    return { message: 'Account updated' };
  },

  deleteAccount: async (
    _legacyBackendId: string,
    accountId: string,
  ): Promise<void> => {
    await aiAccountsClient.deleteBackend(accountId);
  },

  // Forward all management operations to backendManagementApi for backwards compat.
  installCli: backendManagementApi.installCli,
  check: backendManagementApi.check,
  startConnect: backendManagementApi.startConnect,
  streamConnectUrl: backendManagementApi.streamConnectUrl,
  respondConnect: backendManagementApi.respondConnect,
  cancelConnect: backendManagementApi.cancelConnect,
  checkUsage: backendManagementApi.checkUsage,
  checkRateLimits: backendManagementApi.checkRateLimits,
  checkAuthStatus: backendManagementApi.checkAuthStatus,
  discoverModels: backendManagementApi.discoverModels,
  proxyLogin: backendManagementApi.proxyLogin,
  geminiAuthStart: backendManagementApi.geminiAuthStart,
  geminiAuthComplete: backendManagementApi.geminiAuthComplete,
  proxyCallbackForward: backendManagementApi.proxyCallbackForward,
  proxyStatus: backendManagementApi.proxyStatus,
  listProxyAccounts: backendManagementApi.listProxyAccounts,
  testPrompt: backendManagementApi.testPrompt,
  streamTestUrl: backendManagementApi.streamTestUrl,
};
