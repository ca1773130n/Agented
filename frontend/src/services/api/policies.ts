/**
 * Policy / governance API module (phase 23).
 *
 * Mirrors budgets.ts: thin wrappers over `apiFetch` for the /admin/policies
 * CRUD + the /admin/policies/decision ASK-resolution route.
 */
import { apiFetch } from './client';
import type { Policy, PolicyInput, PolicyScope, PolicyDecision } from './types/policies';

export const policyApi = {
  /** List policies, optionally filtered by scope. */
  list: (scope?: PolicyScope): Promise<{ policies: Policy[] }> =>
    apiFetch<{ policies: Policy[] }>(
      `/admin/policies${scope ? `?scope=${encodeURIComponent(scope)}` : ''}`,
    ),

  /** Create (no id) or update (id present) a policy. Returns the row. */
  upsert: (policy: PolicyInput): Promise<Policy> =>
    apiFetch<Policy>('/admin/policies', {
      method: 'PUT',
      body: JSON.stringify(policy),
    }),

  /** Delete a policy by id. */
  remove: (id: string): Promise<void> =>
    apiFetch<void>(`/admin/policies/${id}`, { method: 'DELETE' }),

  /** Resolve a pending ASK for a session (the PolicyAskCard action).
   *
   * `askId` (FIX 2 — ask-scoped) echoes the id from the `policy_ask` card so the
   * backend resolves ONLY that ask — never a different or future ask. */
  decide: (
    sessionId: string,
    askId: string,
    decision: PolicyDecision,
    message?: string,
  ): Promise<{ ok: boolean }> =>
    apiFetch<{ ok: boolean }>('/admin/policies/decision', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        ask_id: askId,
        decision,
        ...(message ? { message } : {}),
      }),
    }),
};
