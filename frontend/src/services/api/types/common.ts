/**
 * Shared utility types and constants used across multiple domains.
 */

// Path and schedule types
export type PathType = 'local' | 'github' | 'project';
export type ScheduleType = 'daily' | 'weekly' | 'monthly';

// Available models per backend
export const CLAUDE_MODELS = ['opus', 'sonnet', 'haiku'] as const;
export const OPENCODE_MODELS = ['codex', 'zen'] as const;
export type ClaudeModel = typeof CLAUDE_MODELS[number];
export type OpenCodeModel = typeof OPENCODE_MODELS[number];

// Shared entity types
export type EntityType = 'skill' | 'command' | 'hook' | 'rule';

// Conversation types shared across entities
export type ConversationStatus = 'active' | 'completed' | 'abandoned';

export interface ConversationMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  /** Which backend produced this message (for display name). */
  backend?: string;
}

// Health API types
export interface HealthStatus {
  status: 'ok' | 'degraded' | 'error';
  components: {
    database: {
      status: 'ok' | 'error';
      journal_mode?: string;
      error?: string;
    };
    process_manager: {
      status: 'ok' | 'error';
      active_executions: number;
      active_execution_ids: string[];
    };
  };
}

// System validation types
export interface GitHubValidation {
  url: string;
  valid: boolean;
  owner?: string;
  repo?: string;
}

export interface BackendCheck {
  backend: string;
  installed: boolean;
  version?: string;
  path?: string;
}

export interface PathValidation {
  path: string;
  exists: boolean;
  is_directory: boolean;
  is_file: boolean;
  is_absolute: boolean;
}

// Audit event type
export interface AuditEvent {
  ts: string;
  action: string;
  entity_type: string;
  entity_id: string;
  outcome: string;
  details?: Record<string, unknown>;
}

// Settings types
export interface HarnessPluginSettings {
  plugin_id?: string;
  marketplace_id?: string;
  plugin_name?: string;
}

// Planning types
export interface PlanningStatus {
  grd_init_status: 'none' | 'initializing' | 'ready' | 'failed';
  active_session_id: string | null;
}

export interface InvokePlanningCommandRequest {
  command: string;
  args?: Record<string, string>;
}

// Setup types
export interface SetupQuestion {
  interaction_id: string;
  question_type: 'text' | 'select' | 'multiselect' | 'password';
  prompt: string;
  options?: string[];
}

export interface SetupLogEntry {
  type: 'log' | 'question' | 'complete' | 'error' | 'status';
  content?: string;
  stream?: string;
  interaction_id?: string;
  question_type?: string;
  prompt?: string;
  options?: string[];
  status?: string;
  exit_code?: number;
  error_message?: string;
}

export interface SetupExecution {
  execution_id: string;
  project_id: string;
  status: string;
  command: string;
  started_at: string;
  finished_at?: string;
  exit_code?: number;
  error_message?: string;
  current_question?: SetupQuestion;
}

export interface BundleInstallResponse {
  status: 'installed' | 'already_installed';
  marketplace_created?: boolean;
  marketplace_id?: string;
  plugins_installed?: string[];
  harness_plugin_set?: boolean;
}
