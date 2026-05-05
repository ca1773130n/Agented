import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '../client';
import { triggerEventApi } from '../trigger-events';
import type {
  TriggerEvent,
  TriggerEventListResponse,
  TriggerEventDispatchStatus,
} from '../trigger-events';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('triggerEventApi', () => {
  it('list defaults to limit=50', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [] });
    await triggerEventApi.list('trig-abc');
    expect(apiFetch).toHaveBeenCalledWith('/admin/triggers/trig-abc/events?limit=50');
  });

  it('list passes custom limit and url-encodes the trigger id', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [] });
    await triggerEventApi.list('trig/with space', 10);
    expect(apiFetch).toHaveBeenCalledWith(
      '/admin/triggers/trig%2Fwith%20space/events?limit=10',
    );
  });

  it('list returns the upstream response shape', async () => {
    const expected: TriggerEventListResponse = {
      events: [
        {
          id: 1,
          trigger_id: 'trig-abc',
          received_at: '2026-05-05T10:00:00Z',
          payload: '{"foo":"bar"}',
          signature_header: 'sha256=abc',
          matched: 1,
          dispatch_status: 'fired',
          dispatch_error: null,
        },
      ],
    };
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue(expected);
    const got = await triggerEventApi.list('trig-abc');
    expect(got).toEqual(expected);
  });

  it('get fetches a single event by id', async () => {
    const event: TriggerEvent = {
      id: 42,
      trigger_id: 'trig-abc',
      received_at: '2026-05-05T11:00:00Z',
      payload: '{}',
      signature_header: null,
      matched: 0,
      dispatch_status: 'unmatched',
      dispatch_error: null,
    };
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue(event);
    const got = await triggerEventApi.get(42);
    expect(apiFetch).toHaveBeenCalledWith('/admin/triggers/events/42');
    expect(got).toEqual(event);
  });

  it('replay POSTs to the replay endpoint', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ fired: true });
    const got = await triggerEventApi.replay(7);
    expect(apiFetch).toHaveBeenCalledWith(
      '/admin/triggers/events/7/replay',
      { method: 'POST' },
    );
    expect(got).toEqual({ fired: true });
  });

  it('exposes types compile-time', () => {
    const statuses: TriggerEventDispatchStatus[] = ['fired', 'unmatched', 'skipped', 'error'];
    expect(statuses).toHaveLength(4);
  });
});
