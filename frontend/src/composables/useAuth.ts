/**
 * useAuth — track B, wave 34.
 *
 * Owns the current-user state. The session now lives in an HttpOnly cookie set
 * by the login response (no longer in localStorage); the API client sends it
 * automatically via `credentials: 'include'` and echoes the CSRF token.
 */
import { ref, computed, readonly } from 'vue';
import {
  authApi,
  clearApiKey,
  clearSessionToken,
  getSessionToken,
  setApiKey,
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
    // Session now lives in an HttpOnly cookie (set by the login response) — the
    // token is no longer persisted to localStorage where XSS could read it.
    currentUser.value = result.user;
    return result.user;
  } catch (err) {
    lastError.value = err instanceof Error ? err.message : 'Login failed';
    throw err;
  }
}

async function signup(
  email: string,
  password: string,
  displayName?: string,
): Promise<AuthUser> {
  lastError.value = null;
  try {
    const result = await authApi.signup(email, password, displayName);
    // Session is in the HttpOnly cookie; not persisted to localStorage.
    currentUser.value = result.user;
    // First-admin signup returns the minted admin API key — store it as
    // X-API-Key so subsequent /admin/* calls AND the ai-accounts sidecar
    // (account discovery) are both authorized. Absent for non-first signups.
    if (result.api_key) setApiKey(result.api_key);
    return result.user;
  } catch (err) {
    lastError.value = err instanceof Error ? err.message : 'Signup failed';
    throw err;
  }
}

async function logout(): Promise<void> {
  // Drop any stored X-API-Key BEFORE the revoke call. The onboarding first-admin
  // signup stores the minted admin key there, and the backend resolves X-API-Key
  // BEFORE the cookie session — so if it were still present, the /logout request
  // would be attributed to the key owner and revoke the wrong user's session
  // (and, left behind, would let the next user on this tab act as admin).
  clearApiKey();
  // Best-effort revoke; the cookie is sent automatically. Clear local state +
  // any legacy localStorage token regardless of server response.
  try {
    await authApi.logout(getSessionToken() || undefined);
  } catch {
    // ignore — clearing local state is the source of truth
  }
  clearSessionToken();
  currentUser.value = null;
}

/**
 * Restore the current user on app boot. The session lives in an HttpOnly cookie
 * (auto-sent), so we always probe ``me()`` rather than gating on a localStorage
 * token; a legacy bearer token, if present, is still sent for backward compat.
 */
async function restore(): Promise<void> {
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
    signup,
    logout,
    restore,
  };
}
