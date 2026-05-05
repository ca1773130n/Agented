/**
 * v0.7.1: Trigger Payload Inspector API client.
 *
 * Wraps the admin endpoints that record/list/get/replay incoming
 * trigger payloads (webhooks, GitHub events, manual fires, schedules):
 *   GET  /admin/triggers/{trigger_id}/events
 *   GET  /admin/triggers/events/{event_id}
 *   POST /admin/triggers/events/{event_id}/replay
 *
 * Backed by `trigger_events` (migration 114). Replay re-fires the
 * original payload through ExecutionService.
 */
import { apiFetch } from './client';

export type TriggerEventStatus = 'received' | 'matched' | 'fired' | 'skipped' | 'error';

export interface TriggerEvent {
  id: number;
  trigger_id: string;
  source: string;
  status: TriggerEventStatus | string;
  received_at: string;
  payload: unknown;
  headers: Record<string, string> | null;
  error_message: string | null;
}

export interface TriggerEventListResponse {
  events: TriggerEvent[];
}

export interface TriggerEventReplayResponse {
  fired: boolean;
}

export const triggerEventApi = {
  list(triggerId: string, limit: number = 50): Promise<TriggerEventListResponse> {
    return apiFetch<TriggerEventListResponse>(
      `/admin/triggers/${encodeURIComponent(triggerId)}/events?limit=${limit}`,
    );
  },

  get(eventId: number): Promise<TriggerEvent> {
    return apiFetch<TriggerEvent>(`/admin/triggers/events/${eventId}`);
  },

  replay(eventId: number): Promise<TriggerEventReplayResponse> {
    return apiFetch<TriggerEventReplayResponse>(
      `/admin/triggers/events/${eventId}/replay`,
      { method: 'POST' },
    );
  },
};
