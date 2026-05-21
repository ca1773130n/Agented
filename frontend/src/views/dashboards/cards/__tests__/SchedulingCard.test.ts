/**
 * PR-D — WebMCP regression guard for SchedulingCard.
 *
 * Verification agents call into the `agented_scheduling_get_rotation_status`
 * tool registered by the SchedulingDashboard. The PR-D extraction must
 * preserve that registration verbatim — losing it silently breaks the
 * verification agents but produces no surface error.
 *
 * This test spies on `useWebMcpTool` and asserts the card calls it with
 * the right tool name on mount.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import { defineComponent, h } from 'vue';

const useWebMcpToolSpy = vi.fn();

vi.mock('../../../../composables/useWebMcpTool', () => ({
  useWebMcpTool: (...args: unknown[]) => useWebMcpToolSpy(...args),
}));

vi.mock('../../../../services/api', () => ({
  schedulerApi: { getStatus: vi.fn().mockResolvedValue({ sessions: [], global_summary: { queued: 0, running: 0, stopped: 0 } }) },
  rotationApi: {
    getStatus: vi.fn().mockResolvedValue({
      sessions: [],
      evaluator: { evaluation_interval_seconds: 0, hysteresis_threshold: 0, active_evaluations: 0, evaluation_states: {} },
    }),
    getHistory: vi.fn().mockResolvedValue({ events: [] }),
  },
  triggerApi: { list: vi.fn().mockResolvedValue({ triggers: [] }) },
}));

vi.mock('../../../../components/monitoring/RotationTimelineChart.vue', () => ({
  default: defineComponent({ render: () => h('div') }),
}));

import SchedulingCard from '../SchedulingCard.vue';

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: defineComponent({ render: () => h('div') }) },
      { path: '/trigger/:triggerId', name: 'trigger-dashboard', component: defineComponent({ render: () => h('div') }) },
    ],
  });
}

describe('PR-D SchedulingCard — WebMCP registration', () => {
  beforeEach(() => {
    useWebMcpToolSpy.mockClear();
  });

  it('registers the agented_scheduling_get_rotation_status tool on mount', async () => {
    const router = buildRouter();
    await router.push('/');
    await router.isReady();
    mount(SchedulingCard, { global: { plugins: [router] } });
    await flushPromises();

    expect(useWebMcpToolSpy).toHaveBeenCalled();
    const call = useWebMcpToolSpy.mock.calls.find((args) => {
      const opts = args[0] as { name?: string } | undefined;
      return opts?.name === 'agented_scheduling_get_rotation_status';
    });
    expect(call, 'useWebMcpTool must be called with name=agented_scheduling_get_rotation_status').toBeTruthy();
    const opts = call![0] as { name: string; page: string; execute: () => Promise<unknown> };
    expect(opts.page).toBe('SchedulingDashboard');
    expect(typeof opts.execute).toBe('function');
  });

  it('rendered card exposes the #scheduling anchor id for deep-link scroll', async () => {
    const router = buildRouter();
    await router.push('/');
    await router.isReady();
    const w = mount(SchedulingCard, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.find('#scheduling').exists()).toBe(true);
  });

  it('renders the merged On-Call Policy sub-card with the unpersisted policy input', async () => {
    const router = buildRouter();
    await router.push('/');
    await router.isReady();
    const w = mount(SchedulingCard, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.find('[data-testid="on-call-policy-input"]').exists()).toBe(true);
    // Severity rows from the folded OnCallEscalation reference table.
    const labels = w.findAll('.thresh-sev').map((n) => n.text());
    expect(labels).toEqual(['critical', 'high', 'medium', 'low']);
  });
});
