/**
 * Barrel re-export for all API modules.
 *
 * This file re-exports every symbol from the domain modules so that
 * consumers can import from './api' or './api/index' as a single entry point.
 */

// Client infrastructure
export { API_BASE, ApiError, apiFetch, isAbortError, createAuthenticatedEventSource, createBackoffEventSource } from './client';
export type { AuthenticatedEventSource, AuthenticatedEventSourceOptions, BackoffEventSource, BackoffEventSourceOptions } from './client';

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
export { analyticsApi } from './analytics';
export { monitoringApi } from './monitoring';
export { rotationApi } from './rotation';
export { schedulerApi } from './scheduler';
export { healthApi, versionApi, utilityApi, settingsApi, setupApi } from './system';
export { superAgentApi, superAgentDocumentApi, superAgentSessionApi, agentMessageApi } from './super-agents';
export { workflowApi, workflowExecutionApi } from './workflows';
export { sketchApi } from './sketches';
export { grdApi } from './grd';
export { mcpServerApi } from './mcp-servers';
export { replayApi } from './replay';
export { collaborativeApi } from './collaborative';
export { branchApi } from './conversation-branches';
export { chunkApi } from './chunks';
export { botTemplateApi } from './bot-templates';
export { promptSnippetApi } from './prompt-snippets';
export { specializedBotApi } from './specialized-bots';
export { secretsApi } from './secrets';
export { rbacApi } from './rbac';
export { gitopsApi } from './gitops';
export { integrationApi, slackApi } from './integrations';
export type { Integration, SlackStatus, SlackCommandLog } from './integrations';
export { configExportApi } from './config-export';
export type { ConfigExport } from './config-export';
export { modelPricingApi } from './model-pricing';
export type { ModelPricingInfo, ModelPricingResponse } from './model-pricing';
export { activityFeedApi } from './activity-feed';
export type { Activity, ActivityType, ActivityFeedResponse, ActivityFeedParams } from './activity-feed';
export { projectHealthApi } from './project-health';
export type { ProjectHealthScorecard, HealthCategory, HealthSignal, HealthRecommendation } from './project-health';
export { prAssignmentApi } from './pr-assignment';
export type { OwnershipRule, AssignmentLog, PrAssignmentSettings, CreateRuleRequest } from './pr-assignment';
export { repoBotDefaultsApi } from './repo-bot-defaults';
export { qualityApi } from './quality-ratings';
export type { QualityEntry, BotQualityStats, QualityEntriesResponse, QualityStatsResponse, SubmitRatingRequest } from './quality-ratings';
export { scopeFiltersApi } from './scope-filters';
export type { ScopeFilter, ScopeFilterPattern, ListScopeFiltersResponse, UpsertScopeFilterRequest, UpdateScopeFilterRequest, AddPatternRequest } from './scope-filters';
export { retentionApi } from './retention';
export type { RetentionPolicy, CreateRetentionPolicyRequest } from './retention';
export { versionPinsApi } from './version-pins';
export type { VersionPin, ComponentVersionHistory, PinStatus, ComponentType, VersionPinsListResponse, VersionHistoryResponse, UpgradeAllResponse } from './version-pins';
export { findingsApi } from './findings';
export type { TriageFinding, FindingsListResponse, CreateFindingRequest, UpdateFindingRequest } from './findings';
export { pipeApi } from './bot-pipes';
export type { BotPipe, BotPipeExecution } from './bot-pipes';
export { botMemoryApi } from './bot-memory';
export type {
  MemoryEntry as BotMemoryEntry,
  BotMemorySummary,
  BotMemoryListAllResponse,
  BotMemoryResponse,
  UpsertMemoryEntryRequest,
} from './bot-memory';
export type {
  RepoBotBinding,
  AvailableBot as RepoBotAvailableBot,
  RepoBotDefaultsListResponse,
  CreateRepoBotDefaultRequest,
  CreateRepoBotDefaultResponse,
  ToggleRepoBotDefaultResponse,
  DeleteRepoBotDefaultResponse,
} from './repo-bot-defaults';
export { skillSetsApi } from './skill-sets';
export type { SkillSet } from './skill-sets';
export { payloadTransformerApi } from './payload-transformers';
export type { PayloadTransformer, TransformRuleItem, UpsertTransformerRequest, UpsertTransformerResponse } from './payload-transformers';

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

  // Planning types
  PlanningStatus,
  InvokePlanningCommandRequest,

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

  // Analytics types
  CostDataPoint,
  CostAnalyticsResponse,
  ExecutionDataPoint,
  ExecutionAnalyticsResponse,
  EffectivenessOverTimePoint,
  EffectivenessResponse,

  // Sketch types
  SketchStatus,
  Sketch,

  // MCP Server types
  McpServer,
  ProjectMcpServerDetail,
  McpSyncResult,

  // Health Monitor & Analytics types
  HealthAlert,
  HealthAlertsResponse,
  HealthStatusResponse,
  WeeklyReport,
  SchedulingSuggestion,
  SchedulingSuggestionsResponse,

  // Replay & Diff types
  ReplayComparison,
  DiffLine,
  OutputDiff,
  DiffContextPreview,

  // Collaborative viewer types
  ViewerInfo,
  InlineComment,

  // Conversation branch types
  ConversationBranch,
  BranchMessage,
  BranchTree,

  // Chunk result types
  ChunkResult,
  MergedChunkResults,

  // Bot Template types
  BotTemplate,
  BotTemplateDeployResponse,

  // Prompt Snippet types
  PromptSnippet,
  CreateSnippetRequest,
  UpdateSnippetRequest,

  // Prompt History & Preview types
  PromptHistoryEntry,
  PreviewPromptFullResponse,
  DryRunResponse,

  // Specialized Bot types
  SpecializedBotStatus,
  SpecializedBotHealth,
  ExecutionSearchResult,
  ExecutionSearchResponse,
  ExecutionSearchStats,
} from './types';

// Secrets types
export type { SecretMetadata, VaultStatus, RevealedSecret } from './secrets';

// RBAC types
export type { UserRole, PermissionMatrix } from './rbac';

// GitOps types
export type { GitOpsRepo, SyncLog, SyncResult } from './gitops';

// GRD types (from grd module, not types module)
export type {
  GrdMilestone,
  GrdPhase,
  GrdPlan,
  GrdSyncResult,
  GrdSyncStatus,
} from './grd';

// Onboarding automation API
export { onboardingApi } from './onboarding';
export type {
  OnboardingStep,
  OnboardingTrigger,
  OnboardingConfigResponse,
  OnboardingStepInput,
  SaveOnboardingConfigRequest,
  SaveOnboardingConfigResponse,
  OnboardingRun,
  OnboardingRunsResponse,
} from './onboarding';

export { executionTaggingApi } from './execution-tagging';
export type { ExecutionTag, TaggedExecution } from './execution-tagging';
