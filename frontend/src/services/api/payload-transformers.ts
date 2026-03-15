/**
 * API client for webhook payload transformer rules.
 */

import { apiFetch } from './client';

export interface TransformRuleItem {
  id: string;
  mode: 'jsonpath' | 'jq' | 'rename' | 'extract';
  expression: string;
  output_key: string;
  description: string;
}

export interface PayloadTransformer {
  id?: string;
  trigger_id: string;
  name: string;
  rules: TransformRuleItem[];
  created_at?: string;
  updated_at?: string;
}

export interface UpsertTransformerRequest {
  name?: string;
  rules: TransformRuleItem[];
}

export interface UpsertTransformerResponse {
  message: string;
  transformer: PayloadTransformer;
}

export const payloadTransformerApi = {
  get: (triggerId: string) =>
    apiFetch<PayloadTransformer>(
      `/admin/triggers/${triggerId}/payload-transformer`
    ),

  save: (triggerId: string, payload: UpsertTransformerRequest) =>
    apiFetch<UpsertTransformerResponse>(
      `/admin/triggers/${triggerId}/payload-transformer`,
      { method: 'PUT', body: JSON.stringify(payload) }
    ),

  reset: (triggerId: string) =>
    apiFetch<{ message: string }>(
      `/admin/triggers/${triggerId}/payload-transformer`,
      { method: 'DELETE' }
    ),
};
