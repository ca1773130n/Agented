/**
 * All type declarations, interfaces, and type-related constants for the API layer.
 */

// Types
export type PathType = 'local' | 'github' | 'project';
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

export type ScheduleType = 'daily' | 'weekly' | 'monthly';

// Available models per backend
export const CLAUDE_MODELS = ['opus', 'sonnet', 'haiku'] as const;
export const OPENCODE_MODELS = ['codex', 'zen'] as const;
export type ClaudeModel = typeof CLAUDE_MODELS[number];
export type OpenCodeModel = typeof OPENCODE_MODELS[number];

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
  created_at?: string;
  path_count?: number;
  execution_status?: ExecutionStatus;
  paths?: ProjectPath[];
}

export interface GitHubValidation {
  url: string;
  valid: boolean;
  owner?: string;
  repo?: string;
}

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

// =============================================================================
// Agent Types
// =============================================================================

export type AgentCreationStatus = 'pending' | 'in_progress' | 'completed';
export type ConversationStatus = 'active' | 'completed' | 'abandoned';
export type EffortLevel = 'low' | 'medium' | 'high' | 'max';
export type AgentLayer = 'backend' | 'frontend' | 'design' | 'analysis' | 'test' | 'management' | 'maintenance' | 'data' | 'mobile';
export type TeamMemberRole = 'leader' | 'member';

export interface AgentDocument {
  name: string;
  path?: string;
  type: 'file' | 'url' | 'inline';
  content?: string;
}

export interface Agent {
  id: string;
  name: string;
  description?: string;
  role?: string;
  goals?: string[];
  context?: string;
  backend_type: 'claude' | 'opencode' | 'gemini' | 'codex';
  enabled: number;
  skills?: string[];
  documents?: AgentDocument[];
  system_prompt?: string;
  creation_conversation_id?: string;
  creation_status: AgentCreationStatus;
  triggers?: string[];
  color?: string;
  icon?: string;
  model?: string;
  temperature?: number;
  tools?: string[];
  autonomous?: number;
  allowed_tools?: string[];
  preferred_model?: string;
  effort_level?: EffortLevel;
  layer?: AgentLayer;
  detected_role?: string;
  matched_skills?: string[];
  created_at?: string;
  updated_at?: string;
}

export interface ConversationMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  /** Which backend produced this message (for display name). */
  backend?: string;
}

export interface AgentConversation {
  id: string;
  agent_id?: string;
  status: ConversationStatus;
  messages?: ConversationMessage[];
  messages_parsed?: ConversationMessage[];
  created_at?: string;
  updated_at?: string;
}

export interface SkillInfo {
  name: string;
  description: string;
  source_path?: string;
}

// Skill Conversation API
export interface SkillConversation {
  id: string;
  status: ConversationStatus;
  messages?: ConversationMessage[];
  messages_parsed?: ConversationMessage[];
  created_at?: string;
  updated_at?: string;
}

// Plugin Conversation API
export interface PluginConversation {
  id: string;
  status: ConversationStatus;
  messages?: ConversationMessage[];
  messages_parsed?: ConversationMessage[];
  created_at?: string;
  updated_at?: string;
}

// Hook Conversation API
export interface HookConversation {
  id: string;
  status: ConversationStatus;
  messages_parsed?: ConversationMessage[];
}

// Command Conversation API
export interface CommandConversation {
  id: string;
  status: ConversationStatus;
  messages_parsed?: ConversationMessage[];
}

// Rule Conversation API
export interface RuleConversation {
  id: string;
  status: ConversationStatus;
  messages_parsed?: ConversationMessage[];
}

export interface DesignConversationSummary {
  id: string;
  entity_type: string;
  entity_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

// =============================================================================
// Skills Types
// =============================================================================

export interface UserSkill {
  id: number;
  skill_name: string;
  skill_path: string;
  description?: string;
  enabled: number;
  selected_for_harness: number;
  metadata?: string;
  created_at?: string;
  updated_at?: string;
}

export interface HarnessConfig {
  skills: UserSkill[];
  config_json: string;
}

// File tree node for playground browser
export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  children?: FileNode[];
}

// Skills.sh types
export interface SkillsShResult {
  name: string;
  description?: string;
  source?: string;
  installs?: number;
  detail_url?: string;
  install_cmd?: string;
  installed?: boolean;
}

export interface LoadFromMarketplaceResponse {
  message: string;
  imported_skills: string[];
  plugin_name: string;
  marketplace: string;
}

export interface DeployToMarketplaceResponse {
  message: string;
  plugin_name: string;
  marketplace: string;
  marketplace_url: string;
  config: Record<string, unknown>;
  config_json: string;
  instructions: string[];
}

// =============================================================================
// Team Types
// =============================================================================

export interface TeamMember {
  id: number;
  team_id: string;
  name: string;
  email?: string;
  role: string;
  layer: string;
  description?: string;
  agent_id?: string;
  super_agent_id?: string;
  member_type?: string;        // 'agent' | 'super_agent' | 'manual'
  agent_name?: string;         // from JOIN
  super_agent_name?: string;   // from JOIN
  tier?: string;               // 'leader' | 'senior' | 'member'
  created_at?: string;
}

export interface TeamConnection {
  id: number;
  source_team_id: string;
  target_team_id: string;
  connection_type: string;
  description?: string;
  created_at?: string;
}

export type TopologyType = 'sequential' | 'parallel' | 'coordinator' | 'generator_critic' | 'hierarchical' | 'human_in_loop' | 'composite';
export type TeamEdgeType = 'delegation' | 'reporting' | 'messaging' | 'approval_gate';
export type CanvasEdgeType = 'command' | 'report' | 'peer' | 'inter_team' | 'messaging';
export type EntityType = 'skill' | 'command' | 'hook' | 'rule';

export interface TeamEdge {
  id: number;
  team_id: string;
  source_member_id: number;
  target_member_id: number;
  edge_type: TeamEdgeType;
  label?: string;
  weight: number;
  created_at?: string;
}

export interface TeamAgentAssignment {
  id: number;
  team_id: string;
  agent_id: string;
  entity_type: EntityType;
  entity_id: string;
  entity_name?: string;
  created_at?: string;
}

export interface CanvasPosition {
  x: number;
  y: number;
}

export interface CanvasPositions {
  [agentId: string]: CanvasPosition;
}

export interface TopologyConfig {
  order?: string[];           // sequential
  agents?: string[];          // parallel
  coordinator?: string;       // coordinator
  workers?: string[];         // coordinator
  generator?: string;         // generator_critic
  critic?: string;            // generator_critic
  max_iterations?: number;    // generator_critic
  aggregation?: string;       // parallel
  lead?: string;              // hierarchical
  approval_nodes?: string[];  // human_in_loop
  sub_groups?: {              // composite
    topology: TopologyType;
    config: Record<string, any>;
    members?: string[];
  }[];
  positions?: CanvasPositions; // Canvas node positions
  edges?: { id?: string; source: string; target: string; label?: string; type?: string }[];
}

export interface Team {
  id: string;
  name: string;
  description?: string;
  color: string;
  leader_id?: string;
  leader_name?: string;
  member_count: number;
  source?: string;  // 'ui_created' or 'github_sync'
  topology?: TopologyType;
  topology_config?: string;
  trigger_source?: TriggerSource;
  trigger_config?: string;
  enabled?: number;
  created_at?: string;
  updated_at?: string;
  members?: TeamMember[];
}

// Generated team config types
export interface GeneratedAgentConfig {
  agent_id: string | null;
  name: string;
  role: string;
  valid?: boolean;
  assignments: {
    entity_type: EntityType;
    entity_id: string;
    entity_name: string;
    valid?: boolean;
    needs_creation?: boolean;
  }[];
}

export interface GeneratedTeamConfig {
  name: string;
  description: string;
  topology: TopologyType;
  topology_config: TopologyConfig;
  color: string;
  agents: GeneratedAgentConfig[];
}

// =============================================================================
// Product Types
// =============================================================================

export interface Product {
  id: string;
  name: string;
  description?: string;
  status: string;
  owner_team_id?: string;
  owner_team_name?: string;
  owner_agent_id?: string;
  owner_agent_name?: string;
  project_count: number;
  created_at?: string;
  updated_at?: string;
  projects?: { id: string; name: string; status: string; github_repo?: string }[];
}

export interface ProductDecision {
  id: string;
  product_id: string;
  title: string;
  description?: string;
  rationale?: string;
  decision_type: string;
  status: string;
  decided_by?: string;
  decided_at?: string;
  tags_json?: string;
  context_json?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ProductMilestone {
  id: string;
  product_id: string;
  version: string;
  title: string;
  description?: string;
  status: string;
  target_date?: string;
  completed_date?: string;
  sort_order: number;
  progress_pct: number;
  created_at?: string;
  updated_at?: string;
}

export interface MilestoneProject {
  id: number;
  milestone_id: string;
  project_id: string;
  contribution?: string;
  project_name?: string;
  project_status?: string;
  created_at?: string;
}

export interface ProductHealth {
  health: 'green' | 'yellow' | 'red' | 'neutral';
  reason: string;
  project_count: number;
  active_count: number;
}

export interface MeetingMessage {
  id: string;
  from_agent_id: string;
  to_agent_id?: string;
  message_type: string;
  subject: string;
  content: string;
  priority: string;
  status: string;
  created_at?: string;
}

export interface TokenSpendDay {
  day: string;
  input_tokens: number;
  output_tokens: number;
  total_cost: number;
}

export interface ProductDashboardData {
  product: Product;
  decisions: ProductDecision[];
  milestones: ProductMilestone[];
  health: ProductHealth;
  activity: MeetingMessage[];
  token_spend: TokenSpendDay[];
}

// =============================================================================
// Project Types
// =============================================================================

export interface Project {
  id: string;
  name: string;
  description?: string;
  status: string;
  product_id?: string;
  product_name?: string;
  github_repo?: string;
  owner_team_id?: string;
  owner_team_name?: string;
  local_path?: string;
  clone_path?: string;
  clone_error?: string;
  clone_status?: 'none' | 'cloning' | 'cloned' | 'error';
  last_synced_at?: string;
  team_count: number;
  team_topology_config?: string;
  created_at?: string;
  updated_at?: string;
  teams?: { id: string; name: string; color: string }[];
}

export interface ProjectTeamEdge {
  id: number;
  project_id: string;
  source_team_id: string;
  target_team_id: string;
  edge_type: string;
  label?: string;
  weight: number;
  created_at?: string;
}

export interface ProjectInstallation {
  id: number;
  project_id: string;
  component_type: 'agent' | 'skill' | 'hook' | 'command' | 'rule';
  component_id: string;
  component_name?: string;
  installed_at?: string;
}

// Project skill type
export interface ProjectSkill {
  id: number;
  project_id: string;
  skill_name: string;
  skill_path?: string;
  source: string;  // 'manual', 'team_sync', 'agent_sync'
  created_at?: string;
}

// Deploy result types
export interface ProjectDeployResult {
  project_id: string;
  project_name: string;
  teams_count: number;
  generated: {
    team_name: string;
    folder_name: string;
    files: Record<string, string>;
  }[];
  error?: string;
}

// Harness result types
export interface HarnessStatusResult {
  exists: boolean;
  subdirs?: Record<string, boolean>;
  project_id: string;
  github_repo?: string;
  error?: string;
}

export interface HarnessLoadResult {
  message?: string;
  project_id: string;
  github_repo?: string;
  imported?: {
    agents: string[];
    skills: string[];
    hooks: string[];
    commands: string[];
    teams: string[];
  };
  counts?: Record<string, number>;
  error?: string;
}

export interface HarnessDeployResult {
  message?: string;
  project_id: string;
  github_repo?: string;
  pr_url?: string;
  branch?: string;
  generated?: {
    files_created: string[];
    counts: Record<string, number>;
  };
  error?: string;
}

// =============================================================================
// Plugin Types
// =============================================================================

export interface PluginComponent {
  id: number;
  plugin_id: string;
  name: string;
  type: string;
  content?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Plugin {
  id: string;
  name: string;
  description?: string;
  version: string;
  status: string;
  author?: string;
  component_count: number;
  created_at?: string;
  updated_at?: string;
  components?: PluginComponent[];
}

// =============================================================================
// Plugin Export/Import Types
// =============================================================================

export interface PluginExportRequest {
  team_id: string;
  export_format: 'claude' | 'agented';
  output_dir?: string;
  plugin_id?: string;
}

export interface PluginExportResponse {
  export_path: string;
  plugin_name: string;
  format: string;
  agents: number;
  skills: number;
  commands: number;
  hooks: number;
  rules: number;
}

export interface PluginImportRequest {
  source_path: string;
  plugin_name?: string;
}

export interface PluginImportFromMarketplaceRequest {
  marketplace_id: string;
  remote_plugin_name: string;
}

export interface PluginImportResponse {
  plugin_id: string;
  plugin_name: string;
  agents_imported: number;
  skills_imported: number;
  commands_imported: number;
  hooks_imported: number;
  rules_imported: number;
}

export interface PluginDeployRequest {
  plugin_id: string;
  marketplace_id: string;
  version?: string;
}

export interface PluginDeployResponse {
  message: string;
  marketplace_url: string;
  plugin_name: string;
}

export interface SyncStatus {
  plugin_id: string;
  status: string;
  entities_synced: number;
  last_synced_at: string | null;
  watching: boolean;
}

export interface PluginExportRecord {
  id: number;
  plugin_id: string;
  team_id: string | null;
  export_format: string;
  export_path: string | null;
  status: string;
  version: string;
  last_exported_at: string | null;
}

// =============================================================================
// Hook Types
// =============================================================================

export type HookEvent =
  | 'PreToolUse'
  | 'PostToolUse'
  | 'Stop'
  | 'SubagentStop'
  | 'SessionStart'
  | 'SessionEnd'
  | 'UserPromptSubmit'
  | 'PreCompact'
  | 'Notification';

export interface Hook {
  id: number;
  name: string;
  event: HookEvent;
  description?: string;
  content?: string;
  enabled: number;
  project_id?: string;
  source_path?: string;
  created_at?: string;
  updated_at?: string;
}

// =============================================================================
// Command Types
// =============================================================================

export interface Command {
  id: number;
  name: string;
  description?: string;
  content?: string;
  arguments?: string;  // JSON array
  enabled: number;
  project_id?: string;
  source_path?: string;
  created_at?: string;
  updated_at?: string;
}

// =============================================================================
// Rule Types
// =============================================================================

export type RuleType = 'pre_check' | 'post_check' | 'validation';

export interface Rule {
  id: number;
  name: string;
  description?: string;
  rule_type: RuleType;
  condition?: string;
  action?: string;
  enabled: number;
  project_id?: string;
  source_path?: string;
  created_at?: string;
  updated_at?: string;
}

// =============================================================================
// Marketplace Types
// =============================================================================

export interface Marketplace {
  id: string;
  name: string;
  url: string;
  type: string;
  is_default: boolean;
  created_at?: string;
}

export interface MarketplacePlugin {
  id: string;
  marketplace_id: string;
  plugin_id?: string;
  remote_name: string;
  version?: string;
  installed_at?: string;
}

export interface MarketplaceSearchResult {
  name: string;
  description?: string;
  version?: string;
  source?: string;
  installed?: boolean;
  marketplace_id: string;
  marketplace_name: string;
}

export interface MarketplaceSearchResponse {
  results: MarketplaceSearchResult[];
  total: number;
  query: string;
  type: string;
}

// =============================================================================
// Settings Types
// =============================================================================

export interface HarnessPluginSettings {
  plugin_id?: string;
  marketplace_id?: string;
  plugin_name?: string;
}

// =============================================================================
// Orchestration Types
// =============================================================================

export interface AccountHealth {
  account_id: number;
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
  account_id: number | null;
}

export interface FallbackChain {
  entity_type: string;
  entity_id: string;
  entries: Array<{
    chain_order: number;
    backend_type: string;
    account_id: number | null;
  }>;
}

// =============================================================================
// Budget Types
// =============================================================================

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

// =============================================================================
// Setup Types
// =============================================================================

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

// =============================================================================
// Monitoring Types
// =============================================================================

export interface MonitoringAccountConfig {
  enabled: boolean;
}

export interface MonitoringConfig {
  enabled: boolean;
  polling_minutes: number;
  accounts: Record<string, MonitoringAccountConfig>;
}

export interface ConsumptionRates {
  '24h': number | null;
  '48h': number | null;
  '72h': number | null;
  '96h': number | null;
  '120h': number | null;
  unit?: string;  // '%/hr' for percentage-only mode, 'tok/hr' otherwise
}

export interface EtaProjection {
  status: 'safe' | 'projected' | 'at_limit' | 'no_data';
  message: string;
  eta: string | null;
  minutes_remaining: number | null;
  resets_at: string | null;
}

export interface WindowSnapshot {
  account_id: number;
  account_name: string;
  plan?: string;
  backend_type: string;
  window_type: string;
  tokens_used: number;
  tokens_limit: number;
  percentage: number;
  threshold_level: string;
  resets_at: string | null;
  recorded_at: string | null;
  consumption_rates: ConsumptionRates;
  eta: EtaProjection;
  shared_with?: string[];
  no_data?: boolean;
}

export interface MonitoringStatus {
  enabled: boolean;
  polling_minutes: number;
  windows: WindowSnapshot[];
  threshold_alerts: Array<{
    account_id: number;
    window_type: string;
    from_level: string;
    to_level: string;
  }>;
}

export interface SnapshotHistoryEntry {
  tokens_used: number;
  percentage: number;
  recorded_at: string;
}

export interface SnapshotHistory {
  account_id: number;
  window_type: string;
  history: SnapshotHistoryEntry[];
}

// =============================================================================
// AI Backends Types
// =============================================================================

export interface BackendCapabilities {
  supports_json_output: boolean;
  supports_token_usage: boolean;
  supports_streaming: boolean;
  supports_non_interactive: boolean;
  json_output_flag?: string;
  non_interactive_flag?: string;
}

export interface AIBackend {
  id: string;
  name: string;
  type: string;  // 'claude', 'opencode', 'gemini', 'codex'
  description?: string;
  icon?: string;
  documentation_url?: string;
  is_installed: number;
  version?: string;
  models?: string[];  // Parsed from JSON
  capabilities?: BackendCapabilities;
  cli_path?: string;
  account_count?: number;
  account_emails?: string;  // Comma-separated emails from all accounts
  created_at?: string;
  last_used_at?: string;  // MAX(last_used_at) across all accounts
}

export interface RateLimitWindow {
  window_type: string;
  percentage: number;
  resets_at: string | null;
  tokens_used: number;
  tokens_limit: number;
}

export interface BackendAccount {
  id: number;
  backend_id: string;
  account_name: string;
  email?: string;
  config_path?: string;
  api_key_env?: string;
  is_default: number;
  plan?: string;
  usage_data?: Record<string, unknown>;
  created_at?: string;
}

export interface AIBackendWithAccounts extends AIBackend {
  accounts: BackendAccount[];
}

// ========================================
// SuperAgent types
// ========================================
export type SuperAgentStatus = 'active' | 'idle' | 'terminated';
export type SessionStatus = 'active' | 'paused' | 'completed' | 'terminated';
export type DocumentType = 'SOUL' | 'IDENTITY' | 'MEMORY' | 'ROLE';
export type AgentMessageType = 'message' | 'broadcast' | 'request' | 'response' | 'artifact' | 'shutdown';
export type AgentMessagePriority = 'low' | 'normal' | 'high';
export type AgentMessageStatus = 'pending' | 'delivered' | 'read' | 'expired';

export interface SuperAgent {
  id: string;
  name: string;
  description?: string;
  backend_type: string;
  preferred_model?: string;
  team_id?: string;
  parent_super_agent_id?: string;
  max_concurrent_sessions: number;
  enabled: number;
  config_json?: string;
  created_at?: string;
  updated_at?: string;
}

export interface SuperAgentDocument {
  id: number;
  super_agent_id: string;
  doc_type: DocumentType;
  title: string;
  content: string;
  version: number;
  created_at?: string;
  updated_at?: string;
}

export interface SuperAgentSession {
  id: string;
  super_agent_id: string;
  status: SessionStatus;
  conversation_log?: string;
  summary?: string;
  token_count: number;
  last_compacted_at?: string;
  started_at?: string;
  ended_at?: string;
}

export interface AgentMessage {
  id: string;
  from_agent_id: string;
  to_agent_id?: string;
  message_type: AgentMessageType;
  priority: AgentMessagePriority;
  subject?: string;
  content: string;
  status: AgentMessageStatus;
  ttl_seconds?: number;
  expires_at?: string;
  created_at?: string;
  delivered_at?: string;
  read_at?: string;
}

// ========================================
// Workflow types
// ========================================
export type WorkflowExecutionStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type WorkflowNodeType = 'trigger' | 'skill' | 'command' | 'agent' | 'script' | 'conditional' | 'transform';
export type NodeExecutionStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface Workflow {
  id: string;
  name: string;
  description?: string;
  trigger_type: string;
  trigger_config?: string;
  enabled: number;
  created_at?: string;
  updated_at?: string;
}

export interface WorkflowVersion {
  id: number;
  workflow_id: string;
  version: number;
  graph_json: string;
  created_at?: string;
}

export interface WorkflowExecution {
  id: string;
  workflow_id: string;
  version: number;
  status: WorkflowExecutionStatus;
  input_json?: string;
  output_json?: string;
  error?: string;
  started_at?: string;
  ended_at?: string;
}

export interface WorkflowNodeExecution {
  id: number;
  execution_id: string;
  node_id: string;
  node_type: WorkflowNodeType;
  status: NodeExecutionStatus;
  input_json?: string;
  output_json?: string;
  error?: string;
  started_at?: string;
  ended_at?: string;
}

// ========================================
// Scheduler types
// ========================================

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

// ========================================
// Rotation types
// ========================================

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

// ========================================
// Sketch types
// ========================================
export type SketchStatus = 'draft' | 'classified' | 'routed' | 'in_progress' | 'completed' | 'archived';

export interface Sketch {
  id: string;
  title: string;
  content: string;
  project_id?: string;
  status: SketchStatus;
  classification_json?: string;
  routing_json?: string;
  parent_sketch_id?: string;
  created_at?: string;
  updated_at?: string;
}

// ========================================
// MCP Server types
// ========================================

export interface McpServer {
  id: string;
  name: string;
  display_name: string | null;
  description: string | null;
  server_type: string;
  command: string | null;
  args: string | null;
  env_json: string | null;
  url: string | null;
  headers_json: string | null;
  timeout_ms: number;
  is_preset: number;
  icon: string | null;
  documentation_url: string | null;
  npm_package: string | null;
  enabled: number;
  created_at: string | null;
  updated_at: string | null;
  category: string;
}

export interface ProjectMcpServerDetail extends McpServer {
  project_id: string;
  mcp_server_id: string;
  assignment_enabled: number;
  env_overrides_json: string | null;
  config_override: string | null;
}

export interface McpSyncResult {
  written?: string;
  servers?: number;
  backup?: string | null;
  diff?: string;
  would_write?: string;
  servers_count?: number;
  error?: string;
}
