/**
 * Analytics API module.
 * Provides cost trend, execution volume, and bot effectiveness analytics.
 */
import { apiFetch } from './client';
import type {
  CostAnalyticsResponse,
  ExecutionAnalyticsResponse,
  EffectivenessResponse,
} from './types';

export const analyticsApi = {
  fetchCostAnalytics: async (params?: {
    group_by?: string;
    start_date?: string;
    end_date?: string;
    entity_type?: string;
  }): Promise<CostAnalyticsResponse> => {
    const query = new URLSearchParams();
    if (params?.group_by) query.set('group_by', params.group_by);
    if (params?.start_date) query.set('start_date', params.start_date);
    if (params?.end_date) query.set('end_date', params.end_date);
    if (params?.entity_type) query.set('entity_type', params.entity_type);
    const qs = query.toString();
    return apiFetch<CostAnalyticsResponse>(`/admin/analytics/cost${qs ? `?${qs}` : ''}`);
  },

  fetchExecutionAnalytics: async (params?: {
    group_by?: string;
    start_date?: string;
    end_date?: string;
    trigger_id?: string;
    team_id?: string;
  }): Promise<ExecutionAnalyticsResponse> => {
    const query = new URLSearchParams();
    if (params?.group_by) query.set('group_by', params.group_by);
    if (params?.start_date) query.set('start_date', params.start_date);
    if (params?.end_date) query.set('end_date', params.end_date);
    if (params?.trigger_id) query.set('trigger_id', params.trigger_id);
    if (params?.team_id) query.set('team_id', params.team_id);
    const qs = query.toString();
    return apiFetch<ExecutionAnalyticsResponse>(`/admin/analytics/executions${qs ? `?${qs}` : ''}`);
  },

  fetchEffectiveness: async (params?: {
    trigger_id?: string;
    group_by?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<EffectivenessResponse> => {
    const query = new URLSearchParams();
    if (params?.trigger_id) query.set('trigger_id', params.trigger_id);
    if (params?.group_by) query.set('group_by', params.group_by);
    if (params?.start_date) query.set('start_date', params.start_date);
    if (params?.end_date) query.set('end_date', params.end_date);
    const qs = query.toString();
    return apiFetch<EffectivenessResponse>(`/admin/analytics/effectiveness${qs ? `?${qs}` : ''}`);
  },
};
