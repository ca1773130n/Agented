import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import type { UsageSummaryEntry } from '../../../services/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let chartCalls: { type: string; data: any; options: any }[] = [];
const mockDestroy = vi.fn();

vi.mock('chart.js', () => {
  class MockChart {
    static register = vi.fn();
    destroy = mockDestroy;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    constructor(_canvas: HTMLCanvasElement, config: any) {
      chartCalls.push({ type: config.type, data: config.data, options: config.options });
    }
  }
  return { Chart: MockChart, registerables: [] };
});

import TokenUsageChart from '../TokenUsageChart.vue';

const sampleData: UsageSummaryEntry[] = [
  {
    period_start: '2026-03-01',
    total_cost_usd: 5.25,
    total_input_tokens: 10000,
    total_output_tokens: 5000,
    total_cache_read_tokens: 1000,
    total_cache_creation_tokens: 500,
    execution_count: 3,
    session_count: 2,
    total_turns: 10,
  },
  {
    period_start: '2026-03-02',
    total_cost_usd: 12.50,
    total_input_tokens: 25000,
    total_output_tokens: 12000,
    total_cache_read_tokens: 3000,
    total_cache_creation_tokens: 1000,
    execution_count: 7,
    session_count: 5,
    total_turns: 25,
  },
];

function mountChart(overrides: Record<string, unknown> = {}) {
  return mount(TokenUsageChart, {
    props: {
      data: sampleData,
      ...overrides,
    },
  });
}

describe('TokenUsageChart', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chartCalls = [];
  });

  it('renders canvas element', async () => {
    const wrapper = mountChart();
    await flushPromises();
    expect(wrapper.find('canvas').exists()).toBe(true);
  });

  it('creates a bar chart by default', async () => {
    mountChart();
    await flushPromises();
    expect(chartCalls.length).toBeGreaterThan(0);
    expect(chartCalls[0].type).toBe('bar');
  });

  it('creates a line chart when chartType is line', async () => {
    mountChart({ chartType: 'line' });
    await flushPromises();
    expect(chartCalls.length).toBeGreaterThan(0);
    expect(chartCalls[0].type).toBe('line');
  });

  it('passes cost data sorted by period_start to chart', async () => {
    mountChart();
    await flushPromises();
    const costDataset = chartCalls[0].data.datasets[0];
    expect(costDataset.label).toBe('Cost (USD)');
    // Data should be sorted chronologically
    expect(costDataset.data[0]).toBe(5.25);
    expect(costDataset.data[1]).toBe(12.50);
  });

  it('includes execution count as second dataset', async () => {
    mountChart();
    await flushPromises();
    const execDataset = chartCalls[0].data.datasets[1];
    expect(execDataset.label).toBe('Executions');
    expect(execDataset.data[0]).toBe(3);
    expect(execDataset.data[1]).toBe(7);
  });
});
