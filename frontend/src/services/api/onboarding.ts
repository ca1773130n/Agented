/**
 * API client for onboarding automation configuration and runs.
 */

import { apiFetch } from './client';

export interface OnboardingStep {
  id: string;
  trigger_id: string;
  step_order: number;
  name: string;
  description: string;
  type: 'github' | 'slack' | 'jira' | 'email' | 'custom';
  enabled: boolean;
  delay_minutes: number;
  created_at: string;
  updated_at: string;
}

export interface OnboardingTrigger {
  id: string;
  name: string;
  trigger_source: string;
  enabled: number;
  [key: string]: unknown;
}

export interface OnboardingConfigResponse {
  trigger: OnboardingTrigger | null;
  steps: OnboardingStep[];
}

export interface OnboardingStepInput {
  id?: string;
  step_order: number;
  name: string;
  description?: string;
  type?: string;
  enabled?: boolean;
  delay_minutes?: number;
}

export interface SaveOnboardingConfigRequest {
  trigger_id: string;
  trigger_event?: string;
  enabled?: boolean;
  steps: OnboardingStepInput[];
}

export interface SaveOnboardingConfigResponse {
  message: string;
  trigger: OnboardingTrigger;
  steps: OnboardingStep[];
}

export interface OnboardingRun {
  id: number;
  execution_id: string;
  trigger_id: string;
  trigger_type: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  backend_type: string;
  prompt: string | null;
  exit_code: number | null;
  [key: string]: unknown;
}

export interface OnboardingRunsResponse {
  runs: OnboardingRun[];
  total: number;
}

export const onboardingApi = {
  getConfig: (triggerId?: string): Promise<OnboardingConfigResponse> => {
    const qs = triggerId ? `?trigger_id=${encodeURIComponent(triggerId)}` : '';
    return apiFetch<OnboardingConfigResponse>(`/admin/onboarding/config${qs}`);
  },

  saveConfig: (payload: SaveOnboardingConfigRequest): Promise<SaveOnboardingConfigResponse> =>
    apiFetch<SaveOnboardingConfigResponse>('/admin/onboarding/config', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  getRuns: (triggerId?: string): Promise<OnboardingRunsResponse> => {
    const qs = triggerId ? `?trigger_id=${encodeURIComponent(triggerId)}` : '';
    return apiFetch<OnboardingRunsResponse>(`/admin/onboarding/runs${qs}`);
  },
};
