import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

// Mock Chart.js before importing component
const mockDestroy = vi.fn();
let chartCalls: { config: { data: { datasets: { data: number[] }[] } } }[] = [];

vi.mock('chart.js', () => {
  class MockChart {
    static register = vi.fn();
    destroy = mockDestroy;
    constructor(_canvas: HTMLCanvasElement, config: Record<string, unknown>) {
      chartCalls.push({ config: config as { data: { datasets: { data: number[] }[] } } });
    }
  }
  return { Chart: MockChart, registerables: [] };
});

import RateLimitGauge from '../RateLimitGauge.vue';

function mountGauge(overrides: Record<string, unknown> = {}) {
  return mount(RateLimitGauge, {
    props: {
      percentage: 50,
      label: 'Opus 5 Hour',
      tokensUsed: 500000,
      tokensLimit: 1000000,
      thresholdLevel: 'normal',
      accentColor: '',
      ...overrides,
    },
  });
}

describe('RateLimitGauge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chartCalls = [];
  });

  it('renders percentage text', async () => {
    const wrapper = mountGauge({ percentage: 42 });
    await flushPromises();
    expect(wrapper.find('.gauge-percentage').text()).toBe('42%');
  });

  it('renders label via v-html', async () => {
    const wrapper = mountGauge({ label: '<span class="gauge-model">Opus</span>' });
    await flushPromises();
    expect(wrapper.find('.gauge-label').html()).toContain('gauge-model');
  });

  it('renders token counts when tokensLimit > 0', async () => {
    const wrapper = mountGauge({ tokensUsed: 1500000, tokensLimit: 3000000 });
    await flushPromises();
    expect(wrapper.find('.gauge-tokens').text()).toContain('1.5M');
    expect(wrapper.find('.gauge-tokens').text()).toContain('3.0M');
  });

  it('does not render token counts when tokensLimit is 0', async () => {
    const wrapper = mountGauge({ tokensLimit: 0 });
    await flushPromises();
    expect(wrapper.find('.gauge-tokens').exists()).toBe(false);
  });

  it('applies green color for low percentage (< 50)', async () => {
    const wrapper = mountGauge({ percentage: 30 });
    await flushPromises();
    const style = wrapper.find('.gauge-percentage').attributes('style') || '';
    // Green (#10b981) for normal - style may use hex or rgb
    expect(style).toMatch(/#10b981|rgb\(16,\s*185,\s*129\)/);
  });

  it('applies red color for critical percentage (>= 90)', async () => {
    const wrapper = mountGauge({ percentage: 95 });
    await flushPromises();
    const style = wrapper.find('.gauge-percentage').attributes('style') || '';
    // Red (#ef4444) for critical
    expect(style).toMatch(/#ef4444|rgb\(239,\s*68,\s*68\)/);
  });

  it('applies amber color for warning percentage (75-89)', async () => {
    const wrapper = mountGauge({ percentage: 80 });
    await flushPromises();
    const style = wrapper.find('.gauge-percentage').attributes('style') || '';
    // Amber (#f59e0b) for warning
    expect(style).toMatch(/#f59e0b|rgb\(245,\s*158,\s*11\)/);
  });

  it('creates a doughnut chart on mount', async () => {
    mountGauge({ percentage: 60 });
    await flushPromises();
    expect(chartCalls.length).toBeGreaterThan(0);
    const config = chartCalls[0].config;
    expect(config.data.datasets[0].data[0]).toBe(60);
    expect(config.data.datasets[0].data[1]).toBe(40);
  });
});
