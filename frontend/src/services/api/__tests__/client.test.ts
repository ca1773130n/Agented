import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiFetch, setSessionToken, getSessionToken } from '../client';

// [08.H1-residual] The `x-new-session-token` rotation handler no longer writes
// rotated tokens to localStorage — rotation now happens via the HttpOnly
// session cookie (Set-Cookie). The client still *reads* any pre-migration
// localStorage token for backward-compat, but never persists a new one.
describe('apiFetch — X-New-Session-Token rotation handling', () => {
  beforeEach(() => {
    setSessionToken('initial-token');
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does NOT persist a rotated token from X-New-Session-Token (cookie-driven now)', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{}', {
        status: 200,
        headers: {
          'content-type': 'application/json',
          'x-new-session-token': 'rotated-token-v2',
        },
      }),
    );
    await apiFetch('/admin/agents');
    // Stored token is untouched — the header is ignored.
    expect(getSessionToken()).toBe('initial-token');
    expect(fetchSpy).toHaveBeenCalled();
  });

  it('leaves stored token untouched when no header', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    await apiFetch('/admin/agents');
    expect(getSessionToken()).toBe('initial-token');
  });

  it('still sends a pre-existing localStorage bearer token for backward-compat', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{}', {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    await apiFetch('/admin/agents');
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers['Authorization']).toBe('Bearer initial-token');
  });
});
