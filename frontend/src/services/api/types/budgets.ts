/**
 * Budget, token usage, and cost tracking types.
 */

export interface BudgetLimit {
  id: number;
  entity_type: string;
  entity_id: string;
  period: string;
  soft_limit_usd: number | null;
  hard_limit_usd: number | null;
  current_spend_usd: number;
  created_at: string;
  updated_at: string;
}

export interface TokenUsageRecord {
  execution_id: string;
  entity_type: string;
  entity_id: string;
  backend_type: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  total_cost_usd: number;
  num_turns: number;
  recorded_at: string;
}

export interface UsageSummaryEntry {
  period_start: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  total_cache_creation_tokens: number;
  execution_count: number;
  session_count: number;
  total_turns: number;
}

export interface EntityUsageEntry {
  entity_id: string;
  entity_name: string;
  entity_type: string;
  total_cost_usd: number;
  execution_count: number;
}

export interface CostEstimate {
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_cost_usd: number;
  model: string;
  confidence: string;
}

export interface BudgetCheck {
  allowed: boolean;
  reason: string;
  remaining_usd: number | null;
  current_spend: number | null;
}

export interface WindowUsageWindow {
  start: string;
  end: string;
  tokens_used: number;
  limit: number;
  percentage: number;
}

export interface WindowUsage {
  five_hour_window: WindowUsageWindow;
  weekly_window: WindowUsageWindow;
}

export interface HistoryStatsPeriod {
  period_start: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  execution_count: number;
  avg_rate_limit_pct: number | null;
  max_rate_limit_pct: number | null;
  snapshot_count: number;
}

export interface HistoryStatsResponse {
  period_type: string;
  periods: HistoryStatsPeriod[];
}

export interface SessionStatsSummary {
  source: string;
  total_sessions: number;
  total_messages: number;
  first_session_date: string | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  total_cache_creation_tokens: number;
  total_cost_usd: number;
  models: Record<string, { input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_creation_tokens: number; cost_usd: number }>;
  daily_activity: { date: string; messageCount: number; sessionCount: number; toolCallCount: number }[];
}
