import { describe, it, expect, beforeEach, vi } from 'vitest';

const loginMock = vi.fn();
const meMock = vi.fn();
const logoutMock = vi.fn();

vi.mock('../../services/api', () => ({
  authApi: {
    login: (...args: unknown[]) => loginMock(...args),
    me: (...args: unknown[]) => meMock(...args),
    logout: (...args: unknown[]) => logoutMock(...args),
  },
  setSessionToken: vi.fn((token: string) => {
    localStorage.setItem('agented-session-token', token);
  }),
  clearSessionToken: vi.fn(() => {
    localStorage.removeItem('agented-session-token');
  }),
  getSessionToken: vi.fn(() => localStorage.getItem('agented-session-token')),
  setApiKey: vi.fn((key: string) => {
    sessionStorage.setItem('agented-api-key', key);
  }),
  clearApiKey: vi.fn(() => {
    sessionStorage.removeItem('agented-api-key');
  }),
}));

import { useAuth } from '../useAuth';

describe('useAuth', () => {
  beforeEach(() => {
    localStorage.clear();
    loginMock.mockReset();
    meMock.mockReset();
    logoutMock.mockReset();
    // Reset module-level state by hitting logout; quick + safe.
    const { logout } = useAuth();
    logout();
  });

  describe('login', () => {
    it('sets current user on success without persisting the token to localStorage', async () => {
      loginMock.mockResolvedValue({
        token: 'tok-123',
        csrf_token: 'csrf-123',
        expires_at: '2099-01-01',
        user: { id: 'user-abc', email: 'a@b.com', display_name: 'A' },
      });
      const { login, currentUser, isAuthenticated } = useAuth();
      const user = await login('a@b.com', 'pw');

      expect(user.id).toBe('user-abc');
      expect(currentUser.value?.id).toBe('user-abc');
      expect(isAuthenticated.value).toBe(true);
      // Session now lives in an HttpOnly cookie — NOT in localStorage.
      expect(localStorage.getItem('agented-session-token')).toBe(null);
    });

    it('rethrows on failure and leaves state empty', async () => {
      loginMock.mockRejectedValue(new Error('Invalid email or password'));
      const { login, currentUser, lastError } = useAuth();

      await expect(login('a@b.com', 'wrong')).rejects.toThrow('Invalid email or password');
      expect(currentUser.value).toBe(null);
      expect(lastError.value).toBe('Invalid email or password');
    });
  });

  describe('logout', () => {
    it('clears the token and currentUser', async () => {
      loginMock.mockResolvedValue({
        token: 'tok-x',
        expires_at: '2099-01-01',
        user: { id: 'user-x', email: 'x@b.com', display_name: null },
      });
      logoutMock.mockResolvedValue(undefined);
      const { login, logout, currentUser } = useAuth();
      await login('x@b.com', 'pw');
      expect(currentUser.value).not.toBe(null);

      await logout();
      expect(currentUser.value).toBe(null);
      expect(localStorage.getItem('agented-session-token')).toBe(null);
    });

    it('clears a stored X-API-Key so admin privileges do not leak to the next user', async () => {
      // The onboarding first-admin signup stores the minted admin key as
      // X-API-Key; since the backend resolves X-API-Key before the cookie
      // session, a leftover key would let the next user on this tab act as admin.
      sessionStorage.setItem('agented-api-key', 'admin-key-xyz');
      logoutMock.mockResolvedValue(undefined);
      const { logout } = useAuth();
      await logout();
      expect(sessionStorage.getItem('agented-api-key')).toBe(null);
    });

    it('clears local state even if server logout fails', async () => {
      loginMock.mockResolvedValue({
        token: 'tok-y',
        expires_at: '2099-01-01',
        user: { id: 'user-y', email: 'y@b.com', display_name: null },
      });
      logoutMock.mockRejectedValue(new Error('boom'));
      const { login, logout, currentUser } = useAuth();
      await login('y@b.com', 'pw');

      await logout();
      expect(currentUser.value).toBe(null);
      expect(localStorage.getItem('agented-session-token')).toBe(null);
    });
  });

  describe('restore', () => {
    it('probes me() via the cookie and stays logged out when there is no session', async () => {
      // Cookie auth: restore always probes me() (the HttpOnly cookie is auto-sent).
      // A bootstrap/api-key caller returns a null id → stays logged out.
      meMock.mockResolvedValue({ id: null, email: null, display_name: null });
      const { restore, currentUser } = useAuth();
      await restore();
      expect(meMock).toHaveBeenCalled();
      expect(currentUser.value).toBe(null);
    });

    it('hydrates currentUser from /api/auth/me when token is valid', async () => {
      localStorage.setItem('agented-session-token', 'live-tok');
      meMock.mockResolvedValue({
        id: 'user-z',
        email: 'z@b.com',
        display_name: 'Z',
        auth_method: 'session',
      });
      const { restore, currentUser } = useAuth();
      await restore();
      expect(currentUser.value?.id).toBe('user-z');
    });

    it('clears the token when /api/auth/me rejects (expired/revoked)', async () => {
      localStorage.setItem('agented-session-token', 'stale-tok');
      meMock.mockRejectedValue(new Error('expired'));
      const { restore, currentUser } = useAuth();
      await restore();
      expect(currentUser.value).toBe(null);
      expect(localStorage.getItem('agented-session-token')).toBe(null);
    });

    it('treats null user_id (api-key/bootstrap caller) as logged-out', async () => {
      localStorage.setItem('agented-session-token', 'odd-tok');
      meMock.mockResolvedValue({ id: null, email: null, display_name: null, auth_method: 'bootstrap' });
      const { restore, currentUser } = useAuth();
      await restore();
      expect(currentUser.value).toBe(null);
    });
  });
});
