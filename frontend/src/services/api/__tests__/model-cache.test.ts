import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '../client';
import { modelCacheApi } from '../model-cache';
import type { ModelCacheResponse } from '../model-cache';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('modelCacheApi', () => {
  it('list defaults auth_method to "unknown"', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await modelCacheApi.list('codex');
    expect(apiFetch).toHaveBeenCalledWith(
      '/admin/backends/codex/models?auth_method=unknown',
    );
  });

  it('list passes through explicit auth_method', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await modelCacheApi.list('codex', 'api_key');
    expect(apiFetch).toHaveBeenCalledWith(
      '/admin/backends/codex/models?auth_method=api_key',
    );
  });

  it('refresh defaults auth_method and uses POST', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await modelCacheApi.refresh('codex');
    expect(apiFetch).toHaveBeenCalledWith(
      '/admin/backends/codex/models/refresh?auth_method=unknown',
      { method: 'POST' },
    );
  });

  it('refresh passes through explicit auth_method', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await modelCacheApi.refresh('claude', 'chatgpt');
    expect(apiFetch).toHaveBeenCalledWith(
      '/admin/backends/claude/models/refresh?auth_method=chatgpt',
      { method: 'POST' },
    );
  });

  it('cacheOverview hits the operator endpoint', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ entries: [] });
    await modelCacheApi.cacheOverview();
    expect(apiFetch).toHaveBeenCalledWith('/admin/backends/models/cache');
  });

  it('returns the upstream response shape', async () => {
    const expected: ModelCacheResponse = {
      models: ['gpt-5'],
      backend_kind: 'codex',
      auth_method: 'api_key',
      discovery_method: 'mixed',
      discovered_at: '2026-05-10T00:00:00+00:00',
      expires_at: '2026-05-17T00:00:00+00:00',
      error_message: null,
      fresh: true,
    };
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue(expected);
    const got = await modelCacheApi.list('codex', 'api_key');
    expect(got).toEqual(expected);
  });

  it('encodes special characters in backend_kind and auth_method', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({});
    await modelCacheApi.list('weird/kind', 'oauth+pkce');
    expect(apiFetch).toHaveBeenCalledWith(
      '/admin/backends/weird%2Fkind/models?auth_method=oauth%2Bpkce',
    );
  });
});
