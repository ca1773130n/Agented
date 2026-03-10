/**
 * API client for trigger condition rules (conditional trigger filtering).
 */

import { apiFetch } from './client';

export interface ConditionItem {
  id: string;
  field: string;
  operator: 'equals' | 'not_equals' | 'contains' | 'greater_than' | 'less_than' | 'matches';
  value: string;
}

export interface TriggerConditionRule {
  id: string;
  trigger_id: string;
  name: string;
  description: string;
  enabled: boolean;
  logic: 'AND' | 'OR';
  conditions: ConditionItem[];
  created_at: string;
  updated_at: string;
}

export interface CreateConditionPayload {
  name: string;
  description?: string;
  enabled?: boolean;
  logic?: 'AND' | 'OR';
  conditions?: ConditionItem[];
}

export interface UpdateConditionPayload {
  name?: string;
  description?: string;
  enabled?: boolean;
  logic?: 'AND' | 'OR';
  conditions?: ConditionItem[];
}

export const triggerConditionsApi = {
  list: (triggerId: string) =>
    apiFetch<{ rules: TriggerConditionRule[]; total: number }>(
      `/admin/triggers/${triggerId}/conditions`
    ),

  create: (triggerId: string, payload: CreateConditionPayload) =>
    apiFetch<{ message: string; rule: TriggerConditionRule }>(
      `/admin/triggers/${triggerId}/conditions`,
      { method: 'POST', body: JSON.stringify(payload) }
    ),

  get: (conditionId: string) =>
    apiFetch<TriggerConditionRule>(`/admin/trigger-conditions/${conditionId}`),

  update: (conditionId: string, payload: UpdateConditionPayload) =>
    apiFetch<TriggerConditionRule>(`/admin/trigger-conditions/${conditionId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  delete: (conditionId: string) =>
    apiFetch<{ message: string }>(`/admin/trigger-conditions/${conditionId}`, {
      method: 'DELETE',
    }),
};
