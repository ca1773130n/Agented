import { describe, it, expect, vi, beforeEach } from 'vitest';
import { shallowMount } from '@vue/test-utils';
import type { MonitoringStatus, SnapshotHistory, WindowSnapshot } from '../../../services/api';

// Mock chart.js (child components import it)
vi.mock('chart.js', () => {
  class MockChart {
    static register = vi.fn();
    destroy = vi.fn();
  }
  return { Chart: MockChart, registerables: [] };
});
vi.mock('chartjs-adapter-date-fns', () => ({}));

import MonitoringSection from '../MonitoringSection.vue';

function makeWindow(overrides: Partial<WindowSnapshot> = {}): WindowSnapshot {
  return {
    account_id: 1,
    account_name: 'Test Account',
    plan: 'max',
    backend_type: 'claude',
    window_type: 'five_hour',
    tokens_used: 5000,
    tokens_limit: 10000,
    percentage: 50,
    threshold_level: 'normal',
    resets_at: new Date(Date.now() + 3600_000).toISOString(),
    recorded_at: new Date().toISOString(),
    consumption_rates: { '24h': 2.5, '48h': 2.0, '72h': null, '96h': null, '120h': null, unit: '%/hr' },
    eta: { status: 'safe', message: 'OK', eta: null, minutes_remaining: 120, resets_at: null },
    ...overrides,
  };
}

function makeStatus(overrides: Partial<MonitoringStatus> = {}): MonitoringStatus {
  return {
    enabled: true,
    polling_minutes: 5,
    windows: [makeWindow()],
    threshold_alerts: [],
    ...overrides,
  };
}

const baseProps = {
  monitoringStatus: null as MonitoringStatus | null,
  monitoringLoading: false,
  pollNowLoading: false,
  monitoringRefreshing: false,
  trendHistories: {} as Record<string, SnapshotHistory>,
  expandedCards: new Set<number>(),
  selectedRateWindows: {} as Record<number, '24h' | '48h' | '72h' | '96h' | '120h'>,
  selectedProjectionWindow: {} as Record<number, string>,
  chartTimeRangeStart: new Date(Date.now() - 86400_000).toISOString(),
  chartTimeRangeEnd: new Date().toISOString(),
};

function mountSection(overrides: Record<string, unknown> = {}) {
  return shallowMount(MonitoringSection, {
    props: { ...baseProps, ...overrides },
  });
}

describe('MonitoringSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders section title', () => {
    const wrapper = mountSection();
    expect(wrapper.text()).toContain('Rate Limit Monitoring');
  });

  it('shows initial loading state when no status and loading', () => {
    const wrapper = mountSection({ monitoringLoading: true, monitoringStatus: null });
    expect(wrapper.find('.monitoring-loading-full').exists()).toBe(true);
    expect(wrapper.text()).toContain('Loading rate limit data');
  });

  it('shows disabled state when monitoring is disabled', () => {
    const wrapper = mountSection({ monitoringStatus: makeStatus({ enabled: false }) });
    expect(wrapper.find('.monitoring-disabled').exists()).toBe(true);
    expect(wrapper.text()).toContain('MANUAL CHECK');
  });

  it('shows disabled state when monitoringStatus is null and not loading', () => {
    const wrapper = mountSection({ monitoringStatus: null, monitoringLoading: false });
    expect(wrapper.find('.monitoring-disabled').exists()).toBe(true);
  });

  it('shows collecting state when enabled but no windows', () => {
    const wrapper = mountSection({ monitoringStatus: makeStatus({ windows: [] }) });
    expect(wrapper.find('.monitoring-collecting').exists()).toBe(true);
    expect(wrapper.text()).toContain('Gauges will appear after the first polling cycle');
  });

  it('renders account cards when monitoring has window data', () => {
    const wrapper = mountSection({ monitoringStatus: makeStatus() });
    expect(wrapper.find('.monitoring-backend-groups').exists()).toBe(true);
    expect(wrapper.find('.monitoring-account-card').exists()).toBe(true);
    expect(wrapper.text()).toContain('Test Account');
  });

  it('shows Active badge when monitoring is enabled', () => {
    const wrapper = mountSection({ monitoringStatus: makeStatus() });
    const badge = wrapper.find('.monitoring-status-badge');
    expect(badge.exists()).toBe(true);
    expect(badge.text()).toBe('Active');
    expect(badge.classes()).toContain('active');
  });

  it('shows Check Now button and emits poll-now on click', async () => {
    const wrapper = mountSection({ monitoringStatus: makeStatus() });
    const btn = wrapper.find('.check-now-btn');
    expect(btn.exists()).toBe(true);
    expect(btn.text()).toContain('Check Now');
    await btn.trigger('click');
    expect(wrapper.emitted('poll-now')).toBeTruthy();
  });

  it('shows Checking text when pollNowLoading is true', () => {
    const wrapper = mountSection({ monitoringStatus: makeStatus(), pollNowLoading: true });
    const btn = wrapper.find('.check-now-btn');
    expect(btn.text()).toContain('Checking...');
    expect(btn.attributes('disabled')).toBeDefined();
  });

  it('shows spinner when monitoringRefreshing is true', () => {
    const wrapper = mountSection({ monitoringStatus: makeStatus(), monitoringRefreshing: true });
    expect(wrapper.find('.inline-refresh-spinner').exists()).toBe(true);
  });

  it('emits toggle-card when account card is clicked', async () => {
    const wrapper = mountSection({ monitoringStatus: makeStatus() });
    await wrapper.find('.monitoring-account-card').trigger('click');
    expect(wrapper.emitted('toggle-card')).toBeTruthy();
    expect(wrapper.emitted('toggle-card')![0]).toEqual([1]);
  });

  it('groups multiple accounts by backend type', () => {
    const status = makeStatus({
      windows: [
        makeWindow({ account_id: 1, account_name: 'Claude Acc', backend_type: 'claude' }),
        makeWindow({ account_id: 2, account_name: 'Codex Acc', backend_type: 'codex' }),
      ],
    });
    const wrapper = mountSection({ monitoringStatus: status });
    const groups = wrapper.findAll('.backend-group');
    expect(groups).toHaveLength(2);
    const labels = groups.map(g => g.find('.backend-group-label').text());
    expect(labels).toContain('Claude');
    expect(labels).toContain('Codex');
  });
});
