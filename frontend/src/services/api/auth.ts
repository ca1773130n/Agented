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

  logout: (token: string) =>
    apiFetch<void>('/api/auth/logout', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    }),
};
