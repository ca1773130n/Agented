/**
 * Scheduler types.
 */

export interface SchedulerSession {
  account_id: number;
  account_name?: string;
  state: string;
  stop_reason: string | null;
  stop_window_type: string | null;
  stop_eta_minutes: number | null;
  resume_estimate: string | null;
  consecutive_safe_polls: number;
  updated_at: string | null;
}

export interface SchedulerGlobalSummary {
  total: number;
  queued: number;
  running: number;
  stopped: number;
}

export interface SchedulerStatus {
  enabled: boolean;
  safety_margin_minutes: number;
  resume_hysteresis_polls: number;
  sessions: SchedulerSession[];
  global_summary: SchedulerGlobalSummary;
}
