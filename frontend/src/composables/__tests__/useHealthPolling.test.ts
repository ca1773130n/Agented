import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mockReadiness = vi.fn();

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

vi.mock('../../services/api', () => ({
  healthApi: { readiness: () => mockReadiness() },
  isAbortError: (err: unknown) =>
    err instanceof DOMException && err.name === 'AbortError',
}));

import { useHealthPolling } from '../useHealthPolling';

describe('useHealthPolling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts connected with no health data', () => {
    const { isConnected, systemHealth } = useHealthPolling();
    expect(isConnected.value).toBe(true);
    expect(systemHealth.value).toBeNull();
  });

  it('pollHealth sets systemHealth on success', async () => {
    const health = {
      status: 'ok',
      components: {
        database: { status: 'ok' },
        process_manager: { status: 'ok', active_executions: 2, active_execution_ids: [] },
      },
    };
    mockReadiness.mockResolvedValue(health);

    const { pollHealth, systemHealth, activeExecutionCount, isConnected } = useHealthPolling();
    await pollHealth();

    expect(systemHealth.value).toEqual(health);
    expect(activeExecutionCount.value).toBe(2);
    expect(isConnected.value).toBe(true);
  });

  it('pollHealth sets error state on failure', async () => {
    mockReadiness.mockRejectedValue(new Error('Network error'));

    const { pollHealth, systemHealth, isConnected, activeExecutionCount } = useHealthPolling();
    await pollHealth();

    expect(systemHealth.value?.status).toBe('error');
    expect(isConnected.value).toBe(false);
    expect(activeExecutionCount.value).toBe(0);
  });

  it('healthColor reflects system status', async () => {
    mockReadiness.mockResolvedValue({ status: 'ok', components: {} });

    const { pollHealth, healthColor } = useHealthPolling();
    expect(healthColor.value).toBe('var(--text-tertiary)'); // no health data yet

    await pollHealth();
    expect(healthColor.value).toBe('var(--accent-emerald)');
  });

  it('healthColor returns amber for degraded status', async () => {
    mockReadiness.mockResolvedValue({ status: 'degraded', components: {} });

    const { pollHealth, healthColor } = useHealthPolling();
    await pollHealth();
    expect(healthColor.value).toBe('var(--accent-amber)');
  });

  it('healthTooltip shows checking message when no data', () => {
    const { healthTooltip } = useHealthPolling();
    expect(healthTooltip.value).toBe('Checking system health...');
  });

  it('startPolling calls pollHealth and sets interval', async () => {
    mockReadiness.mockResolvedValue({
      status: 'ok',
      components: { process_manager: { active_executions: 0 } },
    });

    const { startPolling, stopPolling } = useHealthPolling();
    startPolling(5000);

    // Initial poll
    await vi.advanceTimersByTimeAsync(0);
    expect(mockReadiness).toHaveBeenCalledTimes(1);

    // After interval
    await vi.advanceTimersByTimeAsync(5000);
    expect(mockReadiness).toHaveBeenCalledTimes(2);

    stopPolling();
  });

  it('stopPolling clears the interval', async () => {
    mockReadiness.mockResolvedValue({
      status: 'ok',
      components: { process_manager: { active_executions: 0 } },
    });

    const { startPolling, stopPolling } = useHealthPolling();
    startPolling(5000);

    await vi.advanceTimersByTimeAsync(0);
    stopPolling();

    mockReadiness.mockClear();
    await vi.advanceTimersByTimeAsync(10000);
    expect(mockReadiness).not.toHaveBeenCalled();
  });
});
