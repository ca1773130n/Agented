/**
 * Orchestration, fallback chain, and account health types.
 */

export interface AccountHealth {
  account_id: string;
  account_name: string;
  backend_id: string;
  backend_type: string;
  backend_name: string;
  is_rate_limited: boolean;
  rate_limited_until: string | null;
  rate_limit_reason: string | null;
  cooldown_remaining_seconds: number | null;
  total_executions: number;
  last_used_at: string | null;
  is_default: boolean;
  plan: string | null;
}

export interface FallbackChainEntry {
  backend_type: string;
  account_id: string | null;
}

export interface FallbackChain {
  entity_type: string;
  entity_id: string;
  entries: Array<{
    chain_order: number;
    backend_type: string;
    account_id: string | null;
  }>;
}
