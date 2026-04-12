import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import ServiceHealthGrid from '../ServiceHealthGrid.vue';
import type { AccountHealth } from '../../../services/api';

const healthyAccount: AccountHealth = {
  account_id: '1',
  account_name: 'Primary Account',
  backend_id: 'bk-001',
  backend_type: 'claude',
  backend_name: 'Claude',
  is_rate_limited: false,
  rate_limited_until: null,
  rate_limit_reason: null,
  cooldown_remaining_seconds: null,
  total_executions: 42,
  last_used_at: new Date(Date.now() - 300_000).toISOString(), // 5 min ago
  is_default: true,
  plan: 'max',
};

const rateLimitedAccount: AccountHealth = {
  account_id: '2',
  account_name: 'Secondary Account',
  backend_id: 'bk-002',
  backend_type: 'opencode',
  backend_name: 'OpenCode',
  is_rate_limited: true,
  rate_limited_until: new Date(Date.now() + 120_000).toISOString(), // 2 min from now
  rate_limit_reason: 'Too many requests',
  cooldown_remaining_seconds: 120,
  total_executions: 15,
  last_used_at: new Date(Date.now() - 60_000).toISOString(),
  is_default: false,
  plan: null,
};

function mountGrid(overrides: Record<string, unknown> = {}) {
  return mount(ServiceHealthGrid, {
    props: {
      accounts: [healthyAccount],
      loading: false,
      ...overrides,
    },
  });
}

describe('ServiceHealthGrid', () => {
  it('renders loading skeleton when loading is true', () => {
    const wrapper = mountGrid({ loading: true });
    expect(wrapper.find('.grid-skeleton').exists()).toBe(true);
    expect(wrapper.findAll('.skeleton-card')).toHaveLength(3);
    expect(wrapper.find('.grid-cards').exists()).toBe(false);
  });

  it('renders empty state when accounts is empty', () => {
    const wrapper = mountGrid({ accounts: [], loading: false });
    expect(wrapper.find('.grid-empty').exists()).toBe(true);
    expect(wrapper.text()).toContain('No accounts in this group');
  });

  it('renders health cards for each account', () => {
    const wrapper = mountGrid({ accounts: [healthyAccount, rateLimitedAccount] });
    const cards = wrapper.findAll('.health-card');
    expect(cards).toHaveLength(2);
  });

  it('shows green status dot for healthy account', () => {
    const wrapper = mountGrid({ accounts: [healthyAccount] });
    expect(wrapper.find('.status-dot.green').exists()).toBe(true);
    expect(wrapper.find('.status-badge.healthy').exists()).toBe(true);
  });

  it('shows red status dot and rate limit info for rate-limited account', () => {
    const wrapper = mountGrid({ accounts: [rateLimitedAccount] });
    expect(wrapper.find('.status-dot.red').exists()).toBe(true);
    expect(wrapper.find('.status-badge.rate-limited').exists()).toBe(true);
    expect(wrapper.find('.rate-limit-info').exists()).toBe(true);
    expect(wrapper.text()).toContain('Too many requests');
  });

  it('emits clear-rate-limit when clear button clicked', async () => {
    const wrapper = mountGrid({ accounts: [rateLimitedAccount] });
    await wrapper.find('.clear-rate-limit-btn').trigger('click');
    expect(wrapper.emitted('clear-rate-limit')).toBeTruthy();
    expect(wrapper.emitted('clear-rate-limit')![0]).toEqual(['2']);
  });

  it('displays default badge for default accounts', () => {
    const wrapper = mountGrid({ accounts: [healthyAccount] });
    expect(wrapper.find('.default-badge').exists()).toBe(true);
    expect(wrapper.find('.default-badge').text()).toBe('Default');
  });

  it('displays plan badge when plan is set', () => {
    const wrapper = mountGrid({ accounts: [healthyAccount] });
    expect(wrapper.find('.plan-badge').exists()).toBe(true);
    expect(wrapper.find('.plan-badge').text()).toBe('max');
  });
});
