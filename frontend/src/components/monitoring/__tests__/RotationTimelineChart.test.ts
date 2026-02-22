import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import type { RotationEvent } from '../../../services/api';

// Capture chart constructor calls
let chartConstructorCalls: any[] = [];
const mockDestroy = vi.fn();

// Mock Chart.js with a proper class
vi.mock('chart.js', () => {
  class MockChart {
    static register = vi.fn();
    destroy: () => void;
    options: any;
    data: any;
    type: string;

    constructor(canvas: any, config: any) {
      this.type = config.type;
      this.data = config.data;
      this.options = config.options;
      this.destroy = mockDestroy;
      chartConstructorCalls.push({ canvas, config, instance: this });
    }
  }

  return {
    Chart: MockChart,
    registerables: [],
  };
});

vi.mock('chartjs-adapter-date-fns', () => ({}));

// Import after mock
import RotationTimelineChart from '../RotationTimelineChart.vue';

function makeSampleEvent(overrides: Partial<RotationEvent> = {}): RotationEvent {
  return {
    id: 'rot-001',
    execution_id: 'exec-abc123',
    from_account_id: 1,
    to_account_id: 2,
    from_account_name: 'Account Alpha',
    to_account_name: 'Account Beta',
    reason: 'rate_limit_approaching',
    urgency: 'high',
    utilization_at_rotation: 85,
    rotation_status: 'completed',
    continuation_execution_id: 'exec-def456',
    created_at: '2026-02-19T10:00:00Z',
    completed_at: '2026-02-19T10:01:00Z',
    ...overrides,
  };
}

describe('RotationTimelineChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chartConstructorCalls = [];
  });

  it('renders empty state when no events', () => {
    const wrapper = mount(RotationTimelineChart, {
      props: { events: [] },
    });

    expect(wrapper.text()).toContain('No rotation events recorded yet');
    expect(wrapper.find('canvas').exists()).toBe(false);
  });

  it('renders chart canvas when events provided', async () => {
    const events: RotationEvent[] = [
      makeSampleEvent({ id: 'rot-001' }),
      makeSampleEvent({ id: 'rot-002', rotation_status: 'failed', created_at: '2026-02-19T11:00:00Z' }),
      makeSampleEvent({ id: 'rot-003', rotation_status: 'pending', created_at: '2026-02-19T12:00:00Z' }),
    ];

    const wrapper = mount(RotationTimelineChart, {
      props: { events },
    });
    await flushPromises();

    expect(wrapper.find('canvas').exists()).toBe(true);
    expect(chartConstructorCalls.length).toBeGreaterThan(0);

    const chartCall = chartConstructorCalls[0];
    expect(chartCall.config.type).toBe('scatter');

    // Should have datasets grouped by status
    const datasets = chartCall.config.data.datasets;
    expect(datasets.length).toBeGreaterThanOrEqual(1);

    // Check that tooltip callbacks exist
    const tooltip = chartCall.config.options?.plugins?.tooltip;
    expect(tooltip?.callbacks?.title).toBeDefined();
    expect(tooltip?.callbacks?.label).toBeDefined();
  });

  it('handles events with null account names gracefully', async () => {
    const events: RotationEvent[] = [
      makeSampleEvent({
        id: 'rot-null',
        from_account_id: null,
        from_account_name: 'Deleted Account',
        to_account_name: 'Account Beta',
      }),
    ];

    // Should not throw
    const wrapper = mount(RotationTimelineChart, {
      props: { events },
    });
    await flushPromises();

    expect(wrapper.find('canvas').exists()).toBe(true);
    expect(chartConstructorCalls.length).toBeGreaterThan(0);

    // Verify account labels include "Deleted Account"
    const chartCall = chartConstructorCalls[0];
    const yLabels = chartCall.config.options?.scales?.y?.labels;
    expect(yLabels).toContain('Deleted Account');
    expect(yLabels).toContain('Account Beta');
  });
});
