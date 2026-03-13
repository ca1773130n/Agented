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

export interface TeamInsightData {
  teamId: string;
  teamName: string;
  totalExecutions: number;
  activeBots: number;
  findingsCount: number;
  criticalFindings: number;
  successRate: number;
  riskScore: number;
  topRisks: string[];
  mostActiveBotName: string;
  weekOverWeekChange: number;
}

export interface OrgFindingData {
  id: string;
  title: string;
  severity: string;
  count: number;
  affectedTeams: string[];
  affectedRepos: string[];
  firstSeen: string;
  lastSeen: string;
}

export interface RepoRiskData {
  repo: string;
  team: string;
  riskScore: number;
  openFindings: number;
  lastScanned: string;
}

export interface CrossTeamInsightsResponse {
  teams: TeamInsightData[];
  org_findings: OrgFindingData[];
  top_risky_repos: RepoRiskData[];
  data_available: boolean;
}
