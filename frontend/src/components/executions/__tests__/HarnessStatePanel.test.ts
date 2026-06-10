import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import HarnessStatePanel from '../HarnessStatePanel.vue';
import { executionApi } from '../../../services/api';

vi.mock('../../../services/api', () => ({
  executionApi: { getState: vi.fn() },
}));

const SNAPSHOT = {
  execution: {
    execution_id: 'exec-1', status: 'running', exit_code: null,
    started_at: '2026-06-10T00:00:00', finished_at: null,
    duration_ms: null, backend_type: 'codex',
  },
  run: { status: 'running', step_cursor: 3, budget_used: 0.9, updated_at: '2026-06-10T00:01:00' },
  latest_checkpoint: { step: 3, created_at: '2026-06-10T00:01:00' },
  checkpoint_count: 3,
  verifications: [
    { id: 1, claim: 'no secrets', status: 'passed', evidence_ref: null, checked_at: '2026-06-10T00:02:00' },
  ],
  per_run_limit_usd: 1.0,
};

describe('HarnessStatePanel', () => {
  let wrappers: Array<{ unmount: () => void }> = [];

  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(executionApi.getState).mockResolvedValue(SNAPSHOT as never);
  });
  afterEach(() => {
    // Unmount every wrapper so no poll interval leaks across tests
    // (no global auto-unmount in this project's Vitest setup).
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  function mountPanel(status = 'running') {
    const wrapper = mount(HarnessStatePanel, {
      props: { executionId: 'exec-1', executionStatus: status },
    });
    wrappers.push(wrapper);
    return wrapper;
  }

  it('renders run state, budget, and verifications', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(executionApi.getState).toHaveBeenCalledWith('exec-1');
    expect(wrapper.text()).toContain('3');           // step cursor
    expect(wrapper.text()).toContain('no secrets');  // verification claim
    expect(wrapper.text()).toContain('0.9');         // budget used
  });

  it('applies warning styling past 80% of the per-run limit', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.find('.budget-warning').exists()).toBe(true); // 0.9 of 1.0
  });

  it('polls every 5s while running and stops when terminal', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(executionApi.getState).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(5000);
    await flushPromises();
    expect(executionApi.getState).toHaveBeenCalledTimes(2);

    // Terminal snapshot stops the poller.
    vi.mocked(executionApi.getState).mockResolvedValue({
      ...SNAPSHOT,
      execution: { ...SNAPSHOT.execution, status: 'success' },
    } as never);
    vi.advanceTimersByTime(5000);
    await flushPromises();
    const after = vi.mocked(executionApi.getState).mock.calls.length;
    vi.advanceTimersByTime(15000);
    await flushPromises();
    expect(vi.mocked(executionApi.getState).mock.calls.length).toBe(after);

    wrapper.unmount(); // must not throw; interval cleared
  });

  it('shows the empty-state when no run row exists', async () => {
    vi.mocked(executionApi.getState).mockResolvedValue({
      ...SNAPSHOT, run: null, latest_checkpoint: null, checkpoint_count: 0, verifications: [],
    } as never);
    const wrapper = mountPanel('success');
    await flushPromises();
    expect(wrapper.find('.harness-state-empty').exists()).toBe(true);
  });
});
