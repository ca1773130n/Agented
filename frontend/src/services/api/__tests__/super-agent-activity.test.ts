import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '../client';
import { superAgentActivityApi } from '../super-agent-activity';
import type {
  SuperAgentActivityEvent,
  SuperAgentRollup,
  SuperAgentStatusPill,
} from '../super-agent-activity';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('superAgentActivityApi', () => {
  describe('list', () => {
    it('hits the activity endpoint with no query params by default', async () => {
      (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [] });
      await superAgentActivityApi.list('sa-1');
      expect(apiFetch).toHaveBeenCalledWith('/admin/super-agents/sa-1/activity');
    });

    it('serialises limit, since, and types', async () => {
      (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [] });
      await superAgentActivityApi.list('sa-1', {
        limit: 50,
        since: '2026-05-10T00:00:00Z',
        types: ['message_turn', 'tool_call'],
      });
      const call = (apiFetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
      expect(call).toContain('/admin/super-agents/sa-1/activity?');
      expect(call).toContain('limit=50');
      expect(call).toContain('since=2026-05-10T00%3A00%3A00Z');
      expect(call).toContain('types=message_turn%2Ctool_call');
    });

    it('encodes super-agent id', async () => {
      (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [] });
      await superAgentActivityApi.list('sa with space');
      expect(apiFetch).toHaveBeenCalledWith(
        '/admin/super-agents/sa%20with%20space/activity',
      );
    });

    it('returns the upstream response shape', async () => {
      const event: SuperAgentActivityEvent = {
        id: 1,
        super_agent_id: 'sa-1',
        session_id: null,
        event_type: 'message_turn',
        recorded_at: '2026-05-10T00:00:00Z',
        payload: '{}',
        cost_tokens_in: null,
        cost_tokens_out: null,
        cost_usd: null,
        status: 'ok',
        error_message: null,
        duration_ms: null,
      };
      (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [event] });
      const got = await superAgentActivityApi.list('sa-1');
      expect(got.events).toHaveLength(1);
      expect(got.events[0].id).toBe(1);
    });
  });

  describe('rollup', () => {
    it('defaults to 7-day window', async () => {
      (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({});
      await superAgentActivityApi.rollup('sa-1');
      expect(apiFetch).toHaveBeenCalledWith(
        '/admin/super-agents/sa-1/rollup?window_days=7',
      );
    });

    it('passes custom window', async () => {
      (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({});
      await superAgentActivityApi.rollup('sa-1', 30);
      expect(apiFetch).toHaveBeenCalledWith(
        '/admin/super-agents/sa-1/rollup?window_days=30',
      );
    });

    it('returns the rollup shape', async () => {
      const expected: SuperAgentRollup = {
        super_agent_id: 'sa-1',
        event_count: 5,
        error_count: 1,
        total_cost_usd: 0.25,
        last_active_at: '2026-05-10T00:00:00Z',
        status_pill: 'healthy',
        cost_per_event_avg: 0.05,
        error_rate: 0.2,
      };
      (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue(expected);
      const got = await superAgentActivityApi.rollup('sa-1');
      expect(got).toEqual(expected);
    });
  });

  describe('listForSession', () => {
    it('defaults to limit=200', async () => {
      (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [] });
      await superAgentActivityApi.listForSession('sess-1');
      expect(apiFetch).toHaveBeenCalledWith(
        '/admin/super-agents/sessions/sess-1/activity?limit=200',
      );
    });

    it('respects custom limit', async () => {
      (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [] });
      await superAgentActivityApi.listForSession('sess-1', 50);
      expect(apiFetch).toHaveBeenCalledWith(
        '/admin/super-agents/sessions/sess-1/activity?limit=50',
      );
    });

    it('encodes the session id', async () => {
      (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [] });
      await superAgentActivityApi.listForSession('sess/1');
      expect(apiFetch).toHaveBeenCalledWith(
        '/admin/super-agents/sessions/sess%2F1/activity?limit=200',
      );
    });
  });

  it('exposes the four status pills', () => {
    const pills: SuperAgentStatusPill[] = ['active', 'errored', 'idle', 'healthy'];
    expect(pills).toHaveLength(4);
  });
});
