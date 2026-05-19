/**
 * Tests for SuperAgentOuroborosRunsPanel (v0.7.95).
 *
 * Verifies: empty state, error state, list rendering, row click
 * navigates to the project session, polling only when an active
 * run exists, and that switching super_agent_id reloads.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import SuperAgentOuroborosRunsPanel from '../SuperAgentOuroborosRunsPanel.vue';

const pushMock = vi.fn();

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock('../../../services/api', () => ({
  superAgentApi: {
    listOuroborosRuns: vi.fn(),
  },
}));

import { superAgentApi } from '../../../services/api';

const mockList = superAgentApi.listOuroborosRuns as ReturnType<typeof vi.fn>;

const runActive = {
  session_id: 'psess-active123',
  project_id: 'proj-alpha',
  status: 'active',
  execution_type: 'goal_loop',
  started_at: new Date(Date.now() - 90_000).toISOString(),
  ended_at: null,
  last_activity_at: new Date(Date.now() - 5_000).toISOString(),
  iteration_count: 3,
};
const runCompleted = {
  session_id: 'psess-done4567',
  project_id: 'proj-alpha',
  status: 'completed',
  execution_type: 'goal_loop',
  started_at: new Date(Date.now() - 3_600_000).toISOString(),
  ended_at: new Date(Date.now() - 1_800_000).toISOString(),
  last_activity_at: new Date(Date.now() - 1_800_000).toISOString(),
  iteration_count: 12,
};

beforeEach(() => {
  vi.clearAllMocks();
  pushMock.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('SuperAgentOuroborosRunsPanel', () => {
  it('shows the empty hint when no runs exist', async () => {
    mockList.mockResolvedValue({ runs: [] });
    const w = mount(SuperAgentOuroborosRunsPanel, {
      props: { superAgentId: 'sa-x' },
    });
    await flushPromises();
    expect(w.find('[data-testid="ouroboros-runs-empty"]').exists()).toBe(true);
    expect(w.text()).toContain('Run Ouroboros');
  });

  it('lists runs and renders status + iteration_count', async () => {
    mockList.mockResolvedValue({ runs: [runActive, runCompleted] });
    const w = mount(SuperAgentOuroborosRunsPanel, {
      props: { superAgentId: 'sa-x' },
    });
    await flushPromises();
    const list = w.find('[data-testid="ouroboros-runs-list"]');
    expect(list.exists()).toBe(true);
    expect(w.find(`[data-testid="ouroboros-row-${runActive.session_id}"]`).exists()).toBe(
      true,
    );
    expect(w.find(`[data-testid="ouroboros-row-${runCompleted.session_id}"]`).exists()).toBe(
      true,
    );
    const html = list.html();
    expect(html).toContain('3'); // iteration_count for active
    expect(html).toContain('12'); // iteration_count for completed
    expect(html).toContain('active');
    expect(html).toContain('completed');
  });

  it('row click navigates to the project session with sessionId query', async () => {
    mockList.mockResolvedValue({ runs: [runActive] });
    const w = mount(SuperAgentOuroborosRunsPanel, {
      props: { superAgentId: 'sa-x' },
    });
    await flushPromises();
    await w.find(`[data-testid="ouroboros-row-${runActive.session_id}"] button`).trigger('click');
    expect(pushMock).toHaveBeenCalledWith({
      name: 'project-management',
      params: { projectId: runActive.project_id },
      query: { sessionId: runActive.session_id, tab: 'sessions' },
    });
  });

  it('renders error state when the API rejects', async () => {
    mockList.mockRejectedValue(new Error('network down'));
    const w = mount(SuperAgentOuroborosRunsPanel, {
      props: { superAgentId: 'sa-x' },
    });
    await flushPromises();
    const err = w.find('[data-testid="ouroboros-runs-error"]');
    expect(err.exists()).toBe(true);
    expect(err.text()).toContain('network down');
  });

  it('polls only when at least one run is active', async () => {
    vi.useFakeTimers();
    // First load returns an active run → poll starts.
    mockList.mockResolvedValueOnce({ runs: [runActive] });
    const w = mount(SuperAgentOuroborosRunsPanel, {
      props: { superAgentId: 'sa-x' },
    });
    await flushPromises();
    expect(mockList).toHaveBeenCalledTimes(1);
    // Next poll cycle returns only the completed run → poll stops.
    mockList.mockResolvedValueOnce({ runs: [runCompleted] });
    await vi.advanceTimersByTimeAsync(7_000);
    expect(mockList).toHaveBeenCalledTimes(2);
    // Now no active runs — the poll handle should have cleared.
    // Advance another full interval and verify NO new call.
    await vi.advanceTimersByTimeAsync(7_000);
    expect(mockList).toHaveBeenCalledTimes(2);
    w.unmount();
  });

  it('reloads when superAgentId prop changes', async () => {
    mockList.mockResolvedValue({ runs: [] });
    const w = mount(SuperAgentOuroborosRunsPanel, {
      props: { superAgentId: 'sa-x' },
    });
    await flushPromises();
    expect(mockList).toHaveBeenCalledWith('sa-x', undefined);
    await w.setProps({ superAgentId: 'sa-y' });
    await flushPromises();
    expect(mockList).toHaveBeenLastCalledWith('sa-y', undefined);
  });

  it('discards a stale response when the SA id changed mid-flight', async () => {
    // Regression for the PR #142 codex MAJOR: a slow in-flight
    // request for sa-old must not overwrite ``runs.value`` after
    // the prop changes to sa-new.
    const stale = {
      session_id: 'psess-stale',
      project_id: 'proj-old',
      status: 'completed',
      execution_type: 'goal_loop',
      started_at: null,
      ended_at: null,
      last_activity_at: null,
      iteration_count: 99,
    };
    const fresh = {
      ...runActive,
      session_id: 'psess-fresh',
      project_id: 'proj-new',
    };

    // First call (sa-old) hangs; second call (sa-new) resolves
    // immediately. After both, manually resolve the first with
    // stale data — the panel must IGNORE it.
    let resolveStale: ((v: { runs: unknown[] }) => void) | null = null;
    mockList
      .mockImplementationOnce(
        () => new Promise(res => {
          resolveStale = res;
        }),
      )
      .mockResolvedValueOnce({ runs: [fresh] });

    const w = mount(SuperAgentOuroborosRunsPanel, {
      props: { superAgentId: 'sa-old' },
    });
    await flushPromises();
    expect(mockList).toHaveBeenCalledWith('sa-old', undefined);

    await w.setProps({ superAgentId: 'sa-new' });
    await flushPromises();
    expect(mockList).toHaveBeenLastCalledWith('sa-new', undefined);
    // Fresh data showing.
    expect(w.html()).toContain('psess-fresh');

    // Now the stale (sa-old) request finally resolves. The
    // panel must NOT replace the fresh data.
    resolveStale!({ runs: [stale] });
    await flushPromises();
    expect(w.html()).not.toContain('psess-stale');
    expect(w.html()).toContain('psess-fresh');
  });
});
