/**
 * Trigger, Execution, LogLine, SSE, and audit-related types.
 */

import type { PathType, ScheduleType } from './common';

export type TriggerSource = 'webhook' | 'github' | 'manual' | 'scheduled';

export interface ExecutionStatus {
  status: 'idle' | 'running' | 'resolving' | 'success' | 'failed' | 'cancelled' | 'interrupted';
  started_at?: string;
  finished_at?: string;
  error_message?: string;
  pr_urls?: string[];
}

export interface ProjectPath {
  id: number;
  local_project_path: string;
  symlink_name?: string;
  path_type: PathType;
  github_repo_url?: string;
  project_id?: string;
  project_name?: string;
  project_github_repo?: string;
  created_at?: string;
}

export interface Trigger {
  id: string;
  name: string;
  prompt_template: string;
  backend_type: 'claude' | 'opencode';
  trigger_source: TriggerSource;

  // Webhook matching configuration
  match_field_path?: string;
  match_field_value?: string;
  text_field_path?: string;
  detection_keyword: string;

  // Deprecated field for backward compatibility
  group_id: number;

  is_predefined: number;
  enabled: number;
  auto_resolve: number;
  schedule_type?: ScheduleType;
  schedule_time?: string;
  schedule_day?: number;
  schedule_timezone?: string;
  next_run_at?: string;
  last_run_at?: string;
  skill_command?: string;
  model?: string;
  execution_mode?: 'direct' | 'team';
  team_id?: string | null;
  timeout_seconds?: number | null;
  webhook_secret?: string | null;
  sigterm_grace_seconds?: number | null;
  created_at?: string;
  path_count?: number;
  execution_status?: ExecutionStatus;
  paths?: ProjectPath[];
}

// Security audit types
export interface Finding {
  package: string;
  current_version: string;
  installed_version?: string;
  vulnerable_version: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  cve?: string;
  ecosystem: string;
  project_path: string;
  fix_command?: string;
  cve_link?: string;
  recommended_version?: string;
  description?: string;
}

export interface AuditRecord {
  audit_id: string;
  project_path: string;
  project_name: string;
  audit_date: string;
  audit_week: string;
  group_id?: string;
  trigger_id: string;
  trigger_name: string;
  total_findings: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  status: 'pass' | 'fail';
  findings?: Finding[];
  findings_count?: number;
  trigger_content?: string | object;
}

export interface SeverityTotals {
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface AuditStats {
  historical: {
    total_audits: number;
    total_findings: number;
    severity_totals: SeverityTotals;
  };
  current: {
    total_findings: number;
    severity_totals: SeverityTotals;
    status: string;
  };
  projects: string[];
}

export interface ProjectInfo {
  project_path: string;
  project_name: string;
  project_type: 'local' | 'github';
  audit_count: number;
  last_audit: string;
  last_status: string;
  registered_by_triggers: string[];
}

// Execution log types
export interface Execution {
  id: number;
  execution_id: string;
  trigger_id: string;
  trigger_name: string;
  trigger_type: 'manual' | 'webhook';
  started_at: string;
  finished_at?: string;
  duration_ms?: number;
  prompt?: string;
  backend_type: 'claude' | 'opencode';
  command?: string;
  status: 'running' | 'success' | 'failed' | 'timeout' | 'cancelled' | 'interrupted';
  exit_code?: number;
  error_message?: string;
  stdout_log?: string;
  stderr_log?: string;
}

export interface LogLine {
  timestamp: string;
  stream: 'stdout' | 'stderr';
  content: string;
}

export interface SSELogEvent {
  type: 'log';
  data: LogLine;
}

export interface SSEStatusEvent {
  type: 'status';
  data: {
    status: string;
    started_at?: string;
    execution_id?: string;
    elapsed_ms?: number;
  };
}

export interface SSECompleteEvent {
  type: 'complete';
  data: {
    status: string;
    exit_code?: number;
    error_message?: string;
    duration_ms?: number;
    finished_at?: string;
  };
}

// PR Review types
export type PRStatus = 'open' | 'merged' | 'closed';
export type ReviewStatusType = 'pending' | 'reviewing' | 'approved' | 'changes_requested' | 'fixed';

export interface PrReview {
  id: number;
  trigger_id: string;
  project_name: string;
  github_repo_url?: string;
  pr_number: number;
  pr_url: string;
  pr_title: string;
  pr_author?: string;
  pr_status: PRStatus;
  review_status: ReviewStatusType;
  review_comment?: string;
  fixes_applied: number;
  fix_comment?: string;
  created_at?: string;
  updated_at?: string;
}

export interface PrReviewStats {
  total_prs: number;
  open_prs: number;
  merged_prs: number;
  closed_prs: number;
  pending_reviews: number;
  approved_reviews: number;
  changes_requested: number;
  fixed_reviews: number;
}

export interface PrHistoryPoint {
  date: string;
  created: number;
  merged: number;
  closed: number;
}
