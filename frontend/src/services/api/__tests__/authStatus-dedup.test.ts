import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// apiFetch is the single network seam; mock it so we can count calls.
const apiFetchMock = vi.fn();
vi.mock('../client', () => ({
  API_BASE: '',
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}));

import { healthApi, invalidateAuthStatus } from '../system';

describe('healthApi.authStatus dedup', () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue({ auth_required: true, authenticated: false });
    invalidateAuthStatus();
  });

  afterEach(() => {
    vi.useRealTimers();
    invalidateAuthStatus();
  });

  it('shares ONE request across concurrent callers (the boot storm)', async () => {
    const results = await Promise.all([
      healthApi.authStatus(),
      healthApi.authStatus(),
      healthApi.authStatus(),
      healthApi.authStatus(),
      healthApi.authStatus(),
    ]);
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(results.every((r) => r.auth_required === true)).toBe(true);
  });

  it('reuses the cached result within the TTL', async () => {
    await healthApi.authStatus();
    await healthApi.authStatus();
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
  });

  it('invalidateAuthStatus forces a fresh request (login/logout state change)', async () => {
    await healthApi.authStatus();
    invalidateAuthStatus();
    await healthApi.authStatus();
    expect(apiFetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not cache a rejected request', async () => {
    apiFetchMock.mockRejectedValueOnce(new Error('network'));
    await expect(healthApi.authStatus()).rejects.toThrow('network');
    // next caller must retry, not replay the cached failure
    await healthApi.authStatus();
    expect(apiFetchMock).toHaveBeenCalledTimes(2);
  });
});
