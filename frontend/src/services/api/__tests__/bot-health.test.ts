import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../client', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '../client';
import { botHealthApi } from '../bot-health';
import type { BotHealthRollup, BotHealthResponse, BotHealthStatus } from '../bot-health';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('botHealthApi', () => {
  it('list defaults to 7-day window', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      window_days: 7,
      rollups: [],
    });
    await botHealthApi.list();
    expect(apiFetch).toHaveBeenCalledWith('/admin/bots/health?window_days=7');
  });

  it('list passes custom window', async () => {
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      window_days: 30,
      rollups: [],
    });
    await botHealthApi.list(30);
    expect(apiFetch).toHaveBeenCalledWith('/admin/bots/health?window_days=30');
  });

  it('returns the upstream response shape', async () => {
    const expected: BotHealthResponse = {
      window_days: 14,
      rollups: [],
    };
    (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue(expected);
    const got = await botHealthApi.list(14);
    expect(got).toEqual(expected);
  });

  it('exposes types compile-time', () => {
    // Type-level guard: BotHealthStatus must accept all four pills.
    const statuses: BotHealthStatus[] = ['healthy', 'degraded', 'down', 'no_recent_runs'];
    expect(statuses).toHaveLength(4);

    const rollup: BotHealthRollup = {
      bot_id: 'bot-1',
      bot_name: 'B',
      success_count: 1,
      fail_count: 0,
      success_rate: 1.0,
      p50_duration_ms: 100,
      p95_duration_ms: 200,
      p99_duration_ms: 300,
      last_run_at: null,
      last_failure_at: null,
      last_failure_message: null,
      status_pill: 'healthy',
    };
    expect(rollup.status_pill).toBe('healthy');
  });
});
