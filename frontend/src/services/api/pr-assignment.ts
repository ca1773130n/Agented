/**
 * PR auto-assignment API module.
 * Provides CRUD for ownership rules and settings management.
 */
import { apiFetch } from './client';

export interface OwnershipRule {
  id: string;
  pattern: string;
  team: string;
  reviewers: string[];
  priority: number;
  created_at?: string;
}

export interface AssignmentLog {
  id: string;
  prNumber: number;
  prTitle: string;
  assignedTo: string[];
  reason: string;
  confidence: number;
  timestamp: string;
}

export interface PrAssignmentSettings {
  pr_assignment_enabled: string;
  pr_assignment_min_confidence: string;
  pr_assignment_max_reviewers: string;
}

export interface CreateRuleRequest {
  pattern: string;
  team: string;
  reviewers: string[];
  priority?: number;
}

export const prAssignmentApi = {
  /** List all ownership rules. */
  listRules: () =>
    apiFetch<{ rules: OwnershipRule[] }>('/api/pr-assignment/rules'),

  /** Create a new ownership rule. */
  createRule: (body: CreateRuleRequest) =>
    apiFetch<OwnershipRule>('/api/pr-assignment/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  /** Delete an ownership rule by ID. */
  deleteRule: (ruleId: string) =>
    apiFetch<{ deleted: boolean; id: string }>(`/api/pr-assignment/rules/${ruleId}`, {
      method: 'DELETE',
    }),

  /** Get PR assignment settings. */
  getSettings: () =>
    apiFetch<PrAssignmentSettings>('/api/pr-assignment/settings'),

  /** Update PR assignment settings. */
  updateSettings: (settings: Partial<PrAssignmentSettings>) =>
    apiFetch<{ updated: Partial<PrAssignmentSettings> }>('/api/pr-assignment/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    }),

  /** List recent assignment activity. */
  listRecent: (limit = 20) =>
    apiFetch<{ assignments: AssignmentLog[] }>(`/api/pr-assignment/recent?limit=${limit}`),
};
