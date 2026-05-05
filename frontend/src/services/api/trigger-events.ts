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
 *
 * Field shape mirrors the raw DB columns surfaced by the admin route:
 * - `payload` is a JSON-encoded string (not a parsed object)
 * - `matched` is 0 or 1
 * - `dispatch_status` is the canonical status enum ('fired' | 'unmatched' | …)
 * - `dispatch_error` is the failure reason when dispatch_status is an error
 * - `signature_header` is the raw HMAC header (or null)
 */
import { apiFetch } from './client';

export type TriggerEventDispatchStatus =
  | 'fired'
  | 'unmatched'
  | 'skipped'
  | 'error'
  | string;

export interface TriggerEvent {
  id: number;
  trigger_id: string | null;
  received_at: string;
  /** JSON-encoded payload string. Parse with JSON.parse() at the call site. */
  payload: string;
  signature_header: string | null;
  matched: 0 | 1;
  dispatch_status: TriggerEventDispatchStatus;
  dispatch_error: string | null;
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
