/**
 * Backend management — Agented-local helpers and UI constants.
 *
 * After T28 (shim deletion), the old `backendApi` grouped CRUD shim is gone.
 * What remains here is:
 *
 *  1. `backendManagementApi` — thin wrapper over Agented's Flask
 *     `/admin/backends/*` endpoints for operations that are NOT part of the
 *     upstream `@ai-accounts` Litestar surface: rate-limit checks, CLI usage
 *     introspection, auth-status polling, model discovery, test prompts,
 *     CLIProxyAPI status/listing, Gemini direct-OAuth. These will live in
 *     Agented as long as the Flask admin API does.
 *
 *  2. `BACKEND_LOGIN_INFO` / `BACKEND_PLAN_OPTIONS` — Agented-local UI
 *     constants for plan dropdowns and the provider-console help links.
 *
 *  3. `aiAccountsClient` — shared `AiAccountsClient` singleton for the
 *     places that cannot use the `useAiAccounts()` composable (module-scope
 *     callers, tests, router guards). In components the preferred path is
 *     still `useAiAccounts().client`.
 *
 *  4. `listGroupedBackends` / `getGroupedBackend` — transitional helpers
 *     that regroup flat `BackendDTO` rows from `/api/v1/backends` into the
 *     legacy "one AIBackend per kind with N accounts" shape that Agented's
 *     existing UI still assumes. These are explicitly marked transitional:
 *     new code should read flat `BackendDTO`s directly.
 */
import { AiAccountsClient, type BackendDTO } from '@ai-accounts/ts-core';
import { API_BASE, apiFetch } from './client';
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
 * Shared `AiAccountsClient` singleton for callers that cannot use the
 * `useAiAccounts()` composable (module-scope code, tests, router guards).
 * Components should prefer `useAiAccounts().client` inside `setup()`.
 */
export const aiAccountsClient = new AiAccountsClient({ baseUrl: '' });

/**
 * Agented-specific backend management operations backed by the Flask
 * `/admin/backends/*` API. None of these live on the upstream ai-accounts
 * Litestar surface — they are Agented-local features (rate-limit polling,
 * CLI usage scraping, model discovery, test prompts, Gemini direct-OAuth,
 * CLIProxyAPI status/listing).
 */
export const backendManagementApi = {
  // Auth status check (credential-based, no subprocess)
  checkAuthStatus: (backendId: string) =>
    apiFetch<{
      backend_type: string;
      accounts: Array<{ account_id: number; name: string; email: string; authenticated: boolean }>;
      login_instruction: string;
    }>(`/admin/backends/${backendId}/auth-status`),

  // Connect (legacy OAuth login) operations — still used by AccountLoginModal.
  // TODO(T29+): Migrate AccountLoginModal to the ai-accounts login flow and
  // delete these four methods.
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

  // Model discovery (CLI-based introspection)
  discoverModels: (backendId: string) =>
    apiFetch<{ models: string[]; backend_id: string }>(`/admin/backends/${backendId}/discover-models`, {
      method: 'POST',
    }),

  // CLIProxyAPI status + listing (Agented-local Flask introspection)
  proxyStatus: () =>
    apiFetch<{ available: boolean; account_count: number; accounts: Array<{ email: string; type: string; disabled: boolean; expired: string }> }>('/admin/backends/proxy/status'),

  listProxyAccounts: () =>
    apiFetch<{ accounts: Array<{ email: string; type: string; disabled: boolean; expired: string }> }>('/admin/backends/proxy/accounts'),

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

  // One-shot prompt testing
  testPrompt: (backendType: string, prompt: string, accountId?: string, model?: string) =>
    apiFetch<{ test_id: string; status: string }>('/admin/backends/test', {
      method: 'POST',
      body: JSON.stringify({ backend_type: backendType, prompt, account_id: accountId, model }),
    }),

  streamTestUrl: (testId: string): string =>
    `${API_BASE}/admin/backends/test/${testId}/stream`,

  // CLI install + check — thin wrappers that forward to the ai-accounts
  // client so callers keep their current error-handling shape.
  installCli: async (legacyBackendId: string): Promise<{ message: string; version?: string; error?: string }> => {
    const kind = legacyIdToKind(legacyBackendId);
    const result = await aiAccountsClient.installBackendCli(kind);
    return {
      message: result.display || (result.success ? 'CLI installed' : 'CLI install failed'),
      version: result.binary_path || undefined,
      error: result.success ? undefined : (result.stderr || result.display || 'install failed'),
    };
  },

  check: async (legacyBackendId: string): Promise<{
    installed: boolean;
    version?: string;
    cli_path?: string;
    capabilities?: BackendCapabilities;
  }> => {
    const kind = legacyIdToKind(legacyBackendId);
    // Find a backend row for this kind so we can call detectBackend with its id
    try {
      const { items } = await aiAccountsClient.listBackends();
      const row = items.find((b) => b.kind === kind);
      if (!row) return { installed: false };
      const det = await aiAccountsClient.detectBackend(row.id);
      return {
        installed: det.installed,
        version: det.version ?? undefined,
        cli_path: det.path ?? undefined,
      };
    } catch {
      return { installed: false };
    }
  },

  // CLIProxyAPI login — forwards to the ai-accounts client.
  proxyLogin: async (backendType?: string, configPath?: string): Promise<{
    status: string;
    message: string;
    oauth_url?: string;
    device_code?: string;
    output?: string[];
  }> => {
    const res = await aiAccountsClient.cliproxyLoginBegin(backendType ?? 'claude', configPath);
    return {
      status: res.status,
      message: res.message,
      oauth_url: res.oauth_url ?? undefined,
      device_code: res.device_code ?? undefined,
    };
  },

  proxyCallbackForward: async (callbackUrl: string): Promise<{ status: string; message: string }> => {
    const res = await aiAccountsClient.cliproxyCallbackForward(callbackUrl);
    return { status: res.status, message: res.message };
  },
};

// =============================================================================
// Transitional grouping helpers
// =============================================================================
//
// Agented's legacy UI displays one "backend card" per CLI kind (claude,
// codex, gemini, opencode) with a list of accounts under it. ai-accounts
// 0.3 is flat — each row in `/api/v1/backends` is one account with a
// `kind` field. Until the remaining views (BackendDetailPage, AIBackendsPage,
// TriggerManagement, GeneralSettings, MultiProviderFallback, and a handful
// of smaller ones) are rewritten to operate on flat DTOs directly, they
// call these helpers to regroup the flat rows into the legacy shape.
//
// New code should NOT use these helpers. Use `useAiAccounts().client`
// or the module-level `aiAccountsClient` singleton instead and iterate
// over flat `BackendDTO[]` directly.

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

export function legacyIdToKind(legacyIdOrKind: string): string {
  return legacyIdOrKind.startsWith('backend-')
    ? legacyIdOrKind.slice('backend-'.length)
    : legacyIdOrKind;
}

export function kindToLegacyId(kind: string): string {
  return `backend-${kind}`;
}

function dtoToAccount(dto: BackendDTO): BackendAccount {
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

async function tryDetect(_kind: string, dtos: BackendDTO[]): Promise<{
  is_installed: number;
  version?: string;
  cli_path?: string;
}> {
  if (dtos.length === 0) return { is_installed: 0 };
  try {
    const det = await aiAccountsClient.detectBackend(dtos[0].id);
    return {
      is_installed: det.installed ? 1 : 0,
      version: det.version ?? undefined,
      cli_path: det.path ?? undefined,
    };
  } catch {
    return { is_installed: 0 };
  }
}

function buildGroupedBackend(kind: string, dtos: BackendDTO[], detection: {
  is_installed: number;
  version?: string;
  cli_path?: string;
  capabilities?: BackendCapabilities;
}): AIBackend {
  const meta = BACKEND_METADATA[kind] ?? { name: kind, description: '', documentation_url: '' };
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
 * Transitional: list flat `BackendDTO` rows and regroup them into the
 * legacy "one AIBackend per kind with N accounts" shape.
 *
 * New code should call `aiAccountsClient.listBackends()` directly and
 * iterate over the flat `BackendDTO[]` it returns.
 */
export async function listGroupedBackends(): Promise<{ backends: AIBackend[] }> {
  const { items } = await aiAccountsClient.listBackends();
  const byKind: Record<string, BackendDTO[]> = {};
  for (const dto of items) {
    const kind = dto.kind ?? '';
    (byKind[kind] ||= []).push(dto);
  }
  const kinds = Array.from(new Set([...KNOWN_KINDS, ...Object.keys(byKind)]));
  const detections = await Promise.all(kinds.map((k) => tryDetect(k, byKind[k] ?? [])));
  const backends = kinds.map((kind, idx) =>
    buildGroupedBackend(kind, byKind[kind] ?? [], detections[idx] ?? { is_installed: 0 }),
  );
  return { backends };
}

/**
 * Transitional: fetch flat rows for one kind and return them in the
 * legacy `AIBackendWithAccounts` shape. `legacyIdOrKind` accepts either
 * `backend-claude` or `claude`.
 */
export async function getGroupedBackend(legacyIdOrKind: string): Promise<AIBackendWithAccounts> {
  const kind = legacyIdToKind(legacyIdOrKind);
  const { items } = await aiAccountsClient.listBackends();
  const kindDtos = items.filter((dto) => dto.kind === kind);
  const detection = await tryDetect(kind, kindDtos);
  const base = buildGroupedBackend(kind, kindDtos, detection);
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
}
