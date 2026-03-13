/**
 * Activity feed API module.
 * Fetches the unified chronological activity feed from persistent audit events.
 */
import { apiFetch } from './client';

export type ActivityType =
  | 'bot_run'
  | 'trigger_fired'
  | 'config_changed'
  | 'team_action'
  | 'execution_failed'
  | 'approval';

export interface Activity {
  id: string;
  type: ActivityType;
  title: string;
  description: string;
  actor: string;
  timestamp: string;
  projectId: string;
  metadata?: Record<string, string | number>;
}

export interface ActivityFeedResponse {
  activities: Activity[];
  total: number;
}

export interface ActivityFeedParams {
  limit?: number;
  offset?: number;
  entity_type?: string;
  actor?: string;
  start_date?: string;
  end_date?: string;
}

export const activityFeedApi = {
  list: async (params?: ActivityFeedParams): Promise<ActivityFeedResponse> => {
    const query = new URLSearchParams();
    if (params?.limit != null) query.set('limit', String(params.limit));
    if (params?.offset != null) query.set('offset', String(params.offset));
    if (params?.entity_type) query.set('entity_type', params.entity_type);
    if (params?.actor) query.set('actor', params.actor);
    if (params?.start_date) query.set('start_date', params.start_date);
    if (params?.end_date) query.set('end_date', params.end_date);
    const qs = query.toString();
    return apiFetch<ActivityFeedResponse>(`/api/activity-feed${qs ? `?${qs}` : ''}`);
  },
};
