/**
 * Regression guard for the Cost-lane "no rate limit monitoring graphs" bug.
 *
 * TokenUsageCard renders the rate-limit monitoring graphs (MonitoringSection)
 * from `monitoringStatus`. On mount that ref must be populated from the fast
 * cached GET /admin/monitoring/status (monitoringApi.getStatus). The live
 * pollNow() is a slow (≤120s) provider round-trip and must NOT be the only
 * populator — otherwise the graphs stay hidden whenever it is slow or fails,
 * even though fresh cached snapshots exist.
 *
 * This test mounts the card with pollNow() REJECTING (simulating a slow/failed
 * live poll) and asserts getStatus() is still called on mount, so the graphs
 * render from cache.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { shallowMount, flushPromises } from '@vue/test-utils';

const { monitoringApi } = vi.hoisted(() => ({
  monitoringApi: {
    getStatus: vi.fn(),
    pollNow: vi.fn(),
    getHistory: vi.fn(),
  },
}));

vi.mock('../../../../services/api', () => ({
  budgetApi: {
    getUsageSummary: vi.fn().mockResolvedValue({ summary: [] }),
    getUsageByEntity: vi.fn().mockResolvedValue({ entities: [] }),
    getLimits: vi.fn().mockResolvedValue({ limits: [] }),
    getSessionStats: vi.fn().mockResolvedValue({ stats: null }),
    getAllTimeSpend: vi.fn().mockResolvedValue({ total_cost_usd: 0 }),
    collectSessions: vi.fn().mockResolvedValue({}),
  },
  agentApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
  teamApi: { list: vi.fn().mockResolvedValue({ teams: [] }) },
  triggerApi: { list: vi.fn().mockResolvedValue({ triggers: [] }) },
  rotationApi: { getStatus: vi.fn().mockResolvedValue({ sessions: [], evaluator: undefined }) },
  monitoringApi,
}));

vi.mock('../../../../composables/useWebMcpTool', () => ({ useWebMcpTool: vi.fn() }));
vi.mock('../../../../composables/useToast', () => ({ useToast: () => vi.fn() }));

import TokenUsageCard from '../TokenUsageCard.vue';

describe('TokenUsageCard — rate-limit graphs load from cache on mount', () => {
  beforeEach(() => {
    monitoringApi.getStatus.mockReset().mockResolvedValue({ enabled: true, polling_minutes: 5, windows: [] });
    monitoringApi.pollNow.mockReset().mockRejectedValue(new Error('live poll timed out'));
    monitoringApi.getHistory.mockReset().mockResolvedValue({ history: [] });
  });

  it('calls getStatus (cached) on mount even when the live pollNow fails', async () => {
    shallowMount(TokenUsageCard);
    await flushPromises();

    // The cached status GET must run on mount so MonitoringSection has data...
    expect(monitoringApi.getStatus).toHaveBeenCalled();
    // ...and it must not depend on the live poll, which we forced to reject.
    expect(monitoringApi.pollNow).toHaveBeenCalled();
  });
});
