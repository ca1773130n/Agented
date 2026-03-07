/**
 * Analytics types (ANA-01, ANA-02, ANA-03).
 */

export interface CostDataPoint {
  entity_type: string;
  entity_id: string;
  period: string;
  total_cost_usd: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
}

export interface CostAnalyticsResponse {
  data: CostDataPoint[];
  period_count: number;
  total_cost: number;
}

export interface ExecutionDataPoint {
  period: string;
  backend_type: string;
  total_executions: number;
  success_count: number;
  failed_count: number;
  cancelled_count: number;
  avg_duration_ms: number | null;
}

export interface ExecutionAnalyticsResponse {
  data: ExecutionDataPoint[];
  period_count: number;
  total_executions: number;
}

export interface EffectivenessOverTimePoint {
  period: string;
  total_reviews: number;
  accepted: number;
  acceptance_rate: number;
}

export interface EffectivenessResponse {
  total_reviews: number;
  accepted: number;
  ignored: number;
  pending: number;
  acceptance_rate: number;
  over_time: EffectivenessOverTimePoint[];
}
