import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch, setSessionToken, getSessionToken } from '../client';

describe('apiFetch — X-New-Session-Token rotation handling', () => {
  beforeEach(() => {
    setSessionToken('initial-token');
    vi.restoreAllMocks();
  });

  it('updates stored token when response includes X-New-Session-Token', async () => {
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
    expect(getSessionToken()).toBe('rotated-token-v2');
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

  it('updates token even when the response is an error status', async () => {
    // Server may rotate on a 4xx response too — frontend should still
    // pick up the new token so subsequent requests use the latest.
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{"error":"FORBIDDEN"}', {
        status: 403,
        headers: {
          'content-type': 'application/json',
          'x-new-session-token': 'rotated-on-403',
        },
      }),
    );
    try { await apiFetch('/admin/agents'); } catch { /* expected */ }
    expect(getSessionToken()).toBe('rotated-on-403');
  });
});
