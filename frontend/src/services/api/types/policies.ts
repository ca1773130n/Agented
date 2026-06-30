/**
 * Policy / governance engine types (phase 23).
 *
 * Mirrors the backend PolicyService row shape + the PolicyVerdict / policy_ask
 * SSE event contract (see policy_service.py).
 */

export type PolicyScope = 'server' | 'team' | 'session';
export type PolicyEffect = 'allow' | 'deny' | 'ask';
export type PolicyDecision = 'approve' | 'deny';

/** Builtin evaluator kinds (the `_BUILTINS` dispatch keys) + the `custom`
 * fall-through that returns the stored effect verbatim. */
export type PolicyKind =
  | 'cost_budget'
  | 'max_tool_calls_per_session'
  | 'ask_on_os_tools'
  | 'enforce_sandbox'
  | 'custom';

/** A persisted policy row as returned by /admin/policies. */
export interface Policy {
  id: string;
  scope: PolicyScope;
  scope_id: string | null;
  kind: PolicyKind | string;
  effect: PolicyEffect;
  params: Record<string, unknown>;
  enabled: number;
  priority: number;
  created_at: string;
  updated_at: string;
}

/** Upsert payload for PUT /admin/policies (omit `id` to create). */
export interface PolicyInput {
  id?: string;
  scope?: PolicyScope;
  scope_id?: string | null;
  kind?: PolicyKind | string;
  effect?: PolicyEffect;
  params?: Record<string, unknown>;
  enabled?: number;
  priority?: number;
}

/** The verdict dict returned by PolicyService.evaluate. */
export interface PolicyVerdict {
  decision: PolicyEffect;
  policy_id: string | null;
  kind: string | null;
  reason: string;
  scope: PolicyScope | null;
}

/** The `policy_ask` SSE event payload the ASK card renders. */
export interface PolicyAskEvent {
  policy_id: string | null;
  kind: string | null;
  reason: string;
  scope: PolicyScope | null;
}
