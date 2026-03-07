/**
 * Rotation types.
 */

export interface RotationSession {
  execution_id: string;
  account_id: number | null;
  trigger_id: string | null;
  backend_type: string | null;
  started_at: string | null;
}

export interface RotationEvaluatorStatus {
  job_id: string;
  evaluation_interval_seconds: number;
  hysteresis_threshold: number;
  active_evaluations: number;
  evaluation_states: Record<string, {
    consecutive_rotate_polls: number;
    last_evaluated: string;
  }>;
}

export interface RotationDashboardStatus {
  sessions: RotationSession[];
  evaluator: RotationEvaluatorStatus;
}

export interface RotationEvent {
  id: string;
  execution_id: string;
  from_account_id: number | null;
  to_account_id: number | null;
  from_account_name: string;
  to_account_name: string;
  reason: string | null;
  urgency: string;
  utilization_at_rotation: number | null;
  rotation_status: string;
  continuation_execution_id: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface RotationHistoryResponse {
  events: RotationEvent[];
}
