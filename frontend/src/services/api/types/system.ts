/**
 * System error logging and autofix types.
 */

export type ErrorSource = 'backend' | 'frontend';
export type ErrorCategory = 'cli_error' | 'proxy_error' | 'streaming_error' | 'runtime_error' | 'frontend_error' | 'db_error';
export type ErrorStatus = 'new' | 'investigating' | 'fixed' | 'ignored';
export type FixTier = 1 | 2;
export type FixStatus = 'pending' | 'running' | 'success' | 'failed';

export interface SystemError {
  id: string;
  timestamp: string;
  source: ErrorSource;
  category: ErrorCategory;
  message: string;
  stack_trace?: string;
  request_id?: string;
  context_json?: string;
  error_hash: string;
  status: ErrorStatus;
  fix_attempt_id?: string;
  created_at?: string;
  updated_at?: string;
}

export interface FixAttempt {
  id: string;
  error_id: string;
  tier: FixTier;
  status: FixStatus;
  action_taken?: string;
  agent_session_id?: string;
  started_at: string;
  completed_at?: string;
  created_at?: string;
}

export interface SystemErrorWithFixes extends SystemError {
  fix_attempts: FixAttempt[];
}

export interface SystemErrorListResponse {
  errors: SystemError[];
  total_count: number;
}

export interface ErrorCountsResponse {
  counts: Record<string, number>;
}

export interface ReportErrorRequest {
  source: ErrorSource;
  category: string;
  message: string;
  stack_trace?: string;
  context_json?: string;
}
