import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

// Mock budgetApi
const mockSetLimit = vi.fn().mockResolvedValue({});
vi.mock('../../../services/api', () => ({
  budgetApi: {
    setLimit: (...args: unknown[]) => mockSetLimit(...args),
  },
}));

// Mock useFocusTrap (it tries to focus elements which happy-dom handles poorly)
vi.mock('../../../composables/useFocusTrap', () => ({
  useFocusTrap: vi.fn(),
}));

import BudgetLimitForm from '../BudgetLimitForm.vue';

const sampleAgents = [
  { id: 'agent-abc', name: 'Security Bot' },
  { id: 'agent-def', name: 'PR Reviewer' },
];

const sampleTeams = [
  { id: 'team-xyz', name: 'Backend Team' },
];

function mountForm(overrides: Record<string, unknown> = {}) {
  return mount(BudgetLimitForm, {
    props: {
      agents: sampleAgents,
      teams: sampleTeams,
      triggers: [],
      ...overrides,
    },
    attachTo: document.body,
  });
}

describe('BudgetLimitForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders create mode title by default', () => {
    const wrapper = mountForm();
    expect(wrapper.text()).toContain('Add Budget Limit');
  });

  it('renders edit mode title when mode is edit', () => {
    const wrapper = mountForm({
      mode: 'edit',
      existingLimit: {
        id: 1,
        entity_type: 'agent',
        entity_id: 'agent-abc',
        period: 'monthly',
        soft_limit_usd: 10,
        hard_limit_usd: 50,
        current_spend_usd: 5,
        created_at: '2026-01-01',
        updated_at: '2026-01-01',
      },
    });
    expect(wrapper.text()).toContain('Edit Budget Limit');
  });

  it('emits cancelled when cancel button is clicked', async () => {
    const wrapper = mountForm();
    const cancelBtn = wrapper.findAll('button').find(b => b.text() === 'Cancel');
    expect(cancelBtn).toBeDefined();
    await cancelBtn!.trigger('click');
    expect(wrapper.emitted('cancelled')).toBeTruthy();
  });

  it('emits cancelled when overlay is clicked', async () => {
    const wrapper = mountForm();
    await wrapper.find('.modal-overlay').trigger('click');
    expect(wrapper.emitted('cancelled')).toBeTruthy();
  });

  it('shows validation error when submitting without entity selection', async () => {
    const wrapper = mountForm();
    // Set a hard limit so we don't hit the "at least one limit" error
    const vm = wrapper.vm as unknown as { hardLimit: string };
    vm.hardLimit = '50';
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('Please select an entity');
    expect(mockSetLimit).not.toHaveBeenCalled();
  });

  it('shows validation error when submitting without any limits', async () => {
    const wrapper = mountForm();
    // Select an entity
    const select = wrapper.find('select');
    await select.setValue('agent-abc');
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('At least one limit');
    expect(mockSetLimit).not.toHaveBeenCalled();
  });

  it('shows validation error when halt threshold < alert threshold', async () => {
    const wrapper = mountForm();
    const select = wrapper.find('select');
    await select.setValue('agent-abc');
    // Use vm to set reactive state directly (setValue on number inputs
    // sets a numeric value which breaks .trim() in the component)
    const vm = wrapper.vm as unknown as { softLimit: string; hardLimit: string };
    vm.softLimit = '100';
    vm.hardLimit = '10';
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('Halt threshold must be >= alert threshold');
    expect(mockSetLimit).not.toHaveBeenCalled();
  });

  it('calls budgetApi.setLimit and emits saved on valid submission', async () => {
    const wrapper = mountForm();
    const select = wrapper.find('select');
    await select.setValue('agent-abc');
    const vm = wrapper.vm as unknown as { softLimit: string; hardLimit: string };
    vm.softLimit = '10';
    vm.hardLimit = '50';
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(mockSetLimit).toHaveBeenCalledWith({
      entity_type: 'agent',
      entity_id: 'agent-abc',
      period: 'monthly',
      soft_limit_usd: 10,
      hard_limit_usd: 50,
    });
    expect(wrapper.emitted('saved')).toBeTruthy();
  });

  it('displays API error on submission failure', async () => {
    mockSetLimit.mockRejectedValueOnce(new Error('Server error'));
    const wrapper = mountForm();
    const select = wrapper.find('select');
    await select.setValue('agent-abc');
    const vm = wrapper.vm as unknown as { hardLimit: string };
    vm.hardLimit = '25';
    await wrapper.find('form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('Server error');
    expect(wrapper.emitted('saved')).toBeFalsy();
  });
});
