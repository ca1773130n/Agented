/**
 * Product, ProductDecision, ProductMilestone, and related types.
 */

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
