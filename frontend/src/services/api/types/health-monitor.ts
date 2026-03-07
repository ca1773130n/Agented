/**
 * Health Monitor & Analytics types.
 */

export interface HealthAlert {
  id: number;
  alert_type: 'consecutive_failure' | 'slow_execution' | 'missing_fire' | 'budget_exceeded';
  trigger_id: string;
  message: string;
  details: string | null;
  severity: 'warning' | 'critical';
  acknowledged: boolean;
  created_at: string;
}

export interface HealthAlertsResponse {
  alerts: HealthAlert[];
}

export interface HealthStatusResponse {
  total_alerts: number;
  critical_count: number;
  warning_count: number;
  last_check_time: string | null;
  alerts: HealthAlert[];
}

export interface WeeklyReport {
  prs_reviewed: number;
  issues_found: number;
  estimated_time_saved_minutes: number;
  top_bots: Array<{ trigger_id: string; name: string; execution_count: number }>;
  bots_needing_attention: Array<{ trigger_id: string; name: string; failure_rate: number; alert_count: number }>;
  period_start: string;
  period_end: string;
}

export interface SchedulingSuggestion {
  type: 'hour' | 'day';
  value: string;
  success_rate: number;
  avg_duration_ms: number | null;
  execution_count: number;
  rationale: string;
}

export interface SchedulingSuggestionsResponse {
  suggestions: SchedulingSuggestion[];
  total_executions_analyzed: number;
  analysis_period_days: number;
  message: string | null;
}
