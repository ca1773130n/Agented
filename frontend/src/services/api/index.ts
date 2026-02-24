/**
 * Barrel re-export for all API modules.
 *
 * This file re-exports every symbol from the domain modules so that
 * consumers can import from './api' or './api/index' as a single entry point.
 */

// Client infrastructure
export { API_BASE, ApiError, apiFetch } from './client';

// Domain API objects (value exports)
export { triggerApi, auditApi, resolveApi, executionApi, prReviewApi } from './triggers';
export { agentApi, agentConversationApi } from './agents';
export { teamApi } from './teams';
export { projectApi } from './projects';
export { productApi } from './products';
export { pluginApi, pluginExportApi, pluginConversationApi } from './plugins';
export { skillsApi, userSkillsApi, skillsShApi, harnessApi, skillConversationApi } from './skills';
export { hookApi, hookConversationApi } from './hooks';
export { commandApi, commandConversationApi } from './commands';
export { ruleApi, ruleConversationApi } from './rules';
export { marketplaceApi } from './marketplace';
export { backendApi, BACKEND_LOGIN_INFO, BACKEND_PLAN_OPTIONS } from './backends';
export { orchestrationApi } from './orchestration';
export { budgetApi } from './budgets';
export { monitoringApi } from './monitoring';
export { rotationApi } from './rotation';
export { schedulerApi } from './scheduler';
export { healthApi, versionApi, utilityApi, settingsApi, setupApi } from './system';
export { superAgentApi, superAgentDocumentApi, superAgentSessionApi, agentMessageApi } from './super-agents';
export { workflowApi, workflowExecutionApi } from './workflows';
export { sketchApi } from './sketches';
export { grdApi } from './grd';
export { mcpServerApi } from './mcp-servers';

// Constant exports from types
export { CLAUDE_MODELS, OPENCODE_MODELS } from './types';

// Type re-exports (verbatimModuleSyntax requires export type)
export type {
  // Core types
  PathType,
  TriggerSource,
  ScheduleType,
  ClaudeModel,
  OpenCodeModel,

  // Trigger types
  ExecutionStatus,
  ProjectPath,
  Trigger,
  GitHubValidation,

  // Audit types
  AuditEvent,
  Finding,
  AuditRecord,
  SeverityTotals,
  AuditStats,
  ProjectInfo,

  // Health types
  HealthStatus,

  // Utility types
  BackendCheck,
  PathValidation,

  // Execution types
  Execution,
  LogLine,
  SSELogEvent,
  SSEStatusEvent,
  SSECompleteEvent,

  // PR Review types
  PRStatus,
  ReviewStatusType,
  PrReview,
  PrReviewStats,
  PrHistoryPoint,

  // Agent types
  AgentCreationStatus,
  ConversationStatus,
  EffortLevel,
  AgentLayer,
  TeamMemberRole,
  AgentDocument,
  Agent,
  ConversationMessage,
  AgentConversation,

  // Skill types
  SkillInfo,
  SkillConversation,
  UserSkill,
  HarnessConfig,
  FileNode,
  SkillsShResult,
  LoadFromMarketplaceResponse,
  DeployToMarketplaceResponse,

  // Plugin types
  PluginConversation,
  PluginComponent,
  Plugin,
  PluginExportRequest,
  PluginExportResponse,
  PluginImportRequest,
  PluginImportFromMarketplaceRequest,
  PluginImportResponse,
  PluginDeployRequest,
  PluginDeployResponse,
  SyncStatus,
  PluginExportRecord,

  // Conversation types
  HookConversation,
  CommandConversation,
  RuleConversation,
  DesignConversationSummary,

  // Team types
  TeamMember,
  TeamConnection,
  TopologyType,
  TeamEdgeType,
  CanvasEdgeType,
  TeamEdge,
  EntityType,
  TeamAgentAssignment,
  CanvasPosition,
  CanvasPositions,
  TopologyConfig,
  Team,
  GeneratedAgentConfig,
  GeneratedTeamConfig,

  // Product types
  Product,
  ProductDecision,
  ProductMilestone,
  MilestoneProject,
  ProductHealth,
  MeetingMessage,
  TokenSpendDay,
  ProductDashboardData,

  // Project types
  Project,
  ProjectTeamEdge,
  ProjectInstallation,
  ProjectSkill,
  ProjectDeployResult,
  HarnessStatusResult,
  HarnessLoadResult,
  HarnessDeployResult,

  // Hook types
  HookEvent,
  Hook,

  // Command types
  Command,

  // Rule types
  RuleType,
  Rule,

  // Marketplace types
  Marketplace,
  MarketplacePlugin,
  MarketplaceSearchResult,
  MarketplaceSearchResponse,

  // Settings types
  HarnessPluginSettings,

  // Orchestration types
  AccountHealth,
  FallbackChainEntry,
  FallbackChain,

  // Budget types
  BudgetLimit,
  TokenUsageRecord,
  UsageSummaryEntry,
  EntityUsageEntry,
  CostEstimate,
  BudgetCheck,
  WindowUsageWindow,
  WindowUsage,
  HistoryStatsPeriod,
  HistoryStatsResponse,
  SessionStatsSummary,

  // Setup types
  SetupQuestion,
  SetupLogEntry,
  SetupExecution,
  BundleInstallResponse,

  // Monitoring types
  MonitoringAccountConfig,
  MonitoringConfig,
  ConsumptionRates,
  EtaProjection,
  WindowSnapshot,
  MonitoringStatus,
  SnapshotHistoryEntry,
  SnapshotHistory,

  // AI Backends types
  BackendCapabilities,
  AIBackend,
  RateLimitWindow,
  BackendAccount,
  AIBackendWithAccounts,

  // SuperAgent types
  SuperAgentStatus,
  SessionStatus,
  DocumentType,
  AgentMessageType,
  AgentMessagePriority,
  AgentMessageStatus,
  SuperAgent,
  SuperAgentDocument,
  SuperAgentSession,
  AgentMessage,

  // Workflow types
  WorkflowExecutionStatus,
  WorkflowNodeType,
  NodeExecutionStatus,
  Workflow,
  WorkflowVersion,
  WorkflowExecution,
  WorkflowNodeExecution,

  // Scheduler types
  SchedulerSession,
  SchedulerGlobalSummary,
  SchedulerStatus,

  // Rotation types
  RotationSession,
  RotationEvaluatorStatus,
  RotationDashboardStatus,
  RotationEvent,
  RotationHistoryResponse,

  // Sketch types
  SketchStatus,
  Sketch,

  // MCP Server types
  McpServer,
  ProjectMcpServerDetail,
  McpSyncResult,
} from './types';

// GRD types (from grd module, not types module)
export type {
  GrdMilestone,
  GrdPhase,
  GrdPlan,
  GrdSyncResult,
  GrdSyncStatus,
} from './grd';
