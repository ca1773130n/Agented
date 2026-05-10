/**
 * v0.7.7: Super-Agent Activity Inspector API client.
 *
 * Wraps three /admin/super-agents endpoints used by the inspector page:
 *   GET /admin/super-agents/{id}/activity   — timeline list (limit/since/types).
 *   GET /admin/super-agents/{id}/rollup     — header-card rollup with status pill.
 *   GET /admin/super-agents/sessions/{session_id}/activity — per-session drill-down.
 */
import { apiFetch } from './client';

export type SuperAgentStatusPill = 'active' | 'errored' | 'idle' | 'healthy';

export interface SuperAgentActivityEvent {
  id: number;
  super_agent_id: string;
  session_id: string | null;
  event_type: string;
  recorded_at: string;
  payload: string;
  cost_tokens_in: number | null;
  cost_tokens_out: number | null;
  cost_usd: number | null;
  status: string;
  error_message: string | null;
  duration_ms: number | null;
}

export interface SuperAgentActivityListResponse {
  events: SuperAgentActivityEvent[];
}

export interface SuperAgentRollup {
  super_agent_id: string;
  event_count: number;
  error_count: number;
  total_cost_usd: number;
  last_active_at: string | null;
  status_pill: SuperAgentStatusPill;
  cost_per_event_avg: number | null;
  error_rate: number | null;
}

export const superAgentActivityApi = {
  list(
    id: string,
    opts: { limit?: number; since?: string; types?: string[] } = {},
  ): Promise<SuperAgentActivityListResponse> {
    const qs = new URLSearchParams();
    if (opts.limit) qs.set('limit', String(opts.limit));
    if (opts.since) qs.set('since', opts.since);
    if (opts.types?.length) qs.set('types', opts.types.join(','));
    const query = qs.toString();
    return apiFetch<SuperAgentActivityListResponse>(
      `/admin/super-agents/${encodeURIComponent(id)}/activity${query ? `?${query}` : ''}`,
    );
  },
  rollup(id: string, windowDays: number = 7): Promise<SuperAgentRollup> {
    return apiFetch<SuperAgentRollup>(
      `/admin/super-agents/${encodeURIComponent(id)}/rollup?window_days=${windowDays}`,
    );
  },
  listForSession(
    sessionId: string,
    limit: number = 200,
  ): Promise<SuperAgentActivityListResponse> {
    return apiFetch<SuperAgentActivityListResponse>(
      `/admin/super-agents/sessions/${encodeURIComponent(sessionId)}/activity?limit=${limit}`,
    );
  },
};
