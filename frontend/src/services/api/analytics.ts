/**
 * Analytics API module — health monitoring, reports, and scheduling suggestions.
 */
import { apiFetch } from './client';
import type {
  HealthAlertsResponse,
  HealthStatusResponse,
  WeeklyReport,
  SchedulingSuggestionsResponse,
} from './types';

export const analyticsApi = {
  fetchHealthAlerts: (params?: { limit?: number; trigger_id?: string; acknowledged?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.limit != null) query.set('limit', String(params.limit));
    if (params?.trigger_id) query.set('trigger_id', params.trigger_id);
    if (params?.acknowledged != null) query.set('acknowledged', String(params.acknowledged));
    const qs = query.toString();
    return apiFetch<HealthAlertsResponse>(`/admin/health-monitor/alerts${qs ? `?${qs}` : ''}`);
  },

  fetchHealthStatus: () =>
    apiFetch<HealthStatusResponse>('/admin/health-monitor/status'),

  acknowledgeAlert: (alertId: number) =>
    apiFetch<void>(`/admin/health-monitor/alerts/${alertId}/acknowledge`, { method: 'POST' }),

  runHealthCheck: () =>
    apiFetch<void>('/admin/health-monitor/check', { method: 'POST' }),

  fetchWeeklyReport: (teamId?: string) =>
    apiFetch<WeeklyReport>(`/admin/health-monitor/report${teamId ? `?team_id=${teamId}` : ''}`),

  fetchSchedulingSuggestions: (triggerId?: string) =>
    apiFetch<SchedulingSuggestionsResponse>(
      `/admin/analytics/scheduling-suggestions${triggerId ? `?trigger_id=${triggerId}` : ''}`
    ),
};
