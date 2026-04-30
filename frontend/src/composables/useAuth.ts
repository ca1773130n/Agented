/**
 * useAuth — track B, wave 34.
 *
 * Owns the session-token lifecycle and the current-user state. Token lives
 * in localStorage so reloads stay authenticated; the API client automatically
 * attaches it as Authorization: Bearer (see services/api/client.ts).
 */
import { ref, computed, readonly } from 'vue';
import {
  authApi,
  setSessionToken,
  clearSessionToken,
  getSessionToken,
  type AuthUser,
} from '../services/api';

const currentUser = ref<AuthUser | null>(null);
const isRestoring = ref(false);
const lastError = ref<string | null>(null);

const isAuthenticated = computed(() => currentUser.value !== null);

async function login(email: string, password: string): Promise<AuthUser> {
  lastError.value = null;
  try {
    const result = await authApi.login(email, password);
    setSessionToken(result.token);
    currentUser.value = result.user;
    return result.user;
  } catch (err) {
    lastError.value = err instanceof Error ? err.message : 'Login failed';
    throw err;
  }
}

async function logout(): Promise<void> {
  const token = getSessionToken();
  // Best-effort revoke; clear local state regardless of server response.
  if (token) {
    try {
      await authApi.logout(token);
    } catch {
      // ignore — clearing the local token is the source of truth
    }
  }
  clearSessionToken();
  currentUser.value = null;
}

/**
 * Restore the current user from the stored token. Call once on app boot.
 * On failure (expired/revoked token) the local state is cleared.
 */
async function restore(): Promise<void> {
  const token = getSessionToken();
  if (!token) {
    currentUser.value = null;
    return;
  }
  isRestoring.value = true;
  try {
    const user = await authApi.me();
    // /api/auth/me returns nulls for api-key/bootstrap callers — only
    // treat the result as "logged in" when there's a real user_id.
    if (user.id) {
      currentUser.value = user;
    } else {
      currentUser.value = null;
      clearSessionToken();
    }
  } catch {
    currentUser.value = null;
    clearSessionToken();
  } finally {
    isRestoring.value = false;
  }
}

export function useAuth() {
  return {
    currentUser: readonly(currentUser),
    isAuthenticated,
    isRestoring: readonly(isRestoring),
    lastError: readonly(lastError),
    login,
    logout,
    restore,
  };
}
