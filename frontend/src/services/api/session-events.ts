/**
 * Session events API client (v0.6.3 — admin-only).
 *
 * Wraps GET /admin/auth/session-events (v0.5.12). Used by the
 * frontend SessionEventsPage operator dashboard.
 */
import { apiFetch } from './client';

export interface SessionEvent {
  id: number;
  session_id: string;
  user_id: string | null;
  event_type: string;
  occurred_at: string;
  ip_address: string | null;
  user_agent: string | null;
  metadata: Record<string, unknown> | null;
}

export interface SessionEventsResponse {
  events: SessionEvent[];
  count: number;
}

export interface SessionEventsFilters {
  user_id?: string;
  session_id?: string;
  event_type?: string;
  limit?: number;
  offset?: number;
}

export const sessionEventsApi = {
  list: (filters: SessionEventsFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.user_id) params.set('user_id', filters.user_id);
    if (filters.session_id) params.set('session_id', filters.session_id);
    if (filters.event_type) params.set('event_type', filters.event_type);
    if (filters.limit !== undefined) params.set('limit', String(filters.limit));
    if (filters.offset !== undefined) params.set('offset', String(filters.offset));
    const qs = params.toString();
    const url = qs
      ? `/admin/auth/session-events?${qs}`
      : '/admin/auth/session-events';
    return apiFetch<SessionEventsResponse>(url);
  },
};
