/**
 * Auth API module (track B, wave 34).
 *
 * Wraps the Litestar /api/auth/* endpoints. Tokens are stored as Bearer
 * credentials and sent via the Authorization header — separate from the
 * X-API-Key path used by the legacy admin key.
 */
import { apiFetch } from './client';

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  auth_method?: 'session' | 'api_key' | 'bootstrap';
}

export interface LoginResponse {
  token: string;
  expires_at: string;
  user: AuthUser;
}

export const authApi = {
  login: (email: string, password: string) =>
    apiFetch<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  signup: (email: string, password: string, displayName?: string) =>
    apiFetch<LoginResponse>('/api/auth/signup', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        display_name: displayName ?? '',
      }),
    }),

  me: (token?: string) => {
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    return apiFetch<AuthUser>('/api/auth/me', { headers });
  },

  logout: (token?: string) =>
    apiFetch<void>('/api/auth/logout', {
      method: 'POST',
      // Cookie auth is the norm now; a legacy bearer token is sent if present.
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    }),

  forgotPassword: (email: string) =>
    apiFetch<void>('/api/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, password: string) =>
    apiFetch<void>('/api/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, password }),
    }),

  /**
   * OIDC SSO start URL (Phase 25, 25-04). Navigating here begins the
   * authorization-code flow; the callback establishes a session cookie and
   * redirects back to the SPA. Only providers listed in
   * `/health/auth-status`'s `oidc_providers` are configured/available.
   */
  oidcStartUrl: (provider: string) => `/api/auth/oidc/${provider}/start`,
};
