import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import PolicyEditor from '../PolicyEditor.vue';

const list = vi.fn();
const upsert = vi.fn((..._a: unknown[]) => Promise.resolve({}));
const remove = vi.fn((..._a: unknown[]) => Promise.resolve());

vi.mock('../../../services/api', () => ({
  policyApi: {
    list: (...a: unknown[]) => list(...a),
    upsert: (...a: unknown[]) => upsert(...a),
    remove: (...a: unknown[]) => remove(...a),
    decide: vi.fn(),
  },
}));

const samplePolicy = {
  id: 'pol-111',
  scope: 'session',
  scope_id: 'sess-x',
  kind: 'cost_budget',
  effect: 'deny',
  params: { max_cost_usd: 5 },
  enabled: 1,
  priority: 3,
  created_at: '',
  updated_at: '',
};

describe('PolicyEditor', () => {
  beforeEach(() => {
    list.mockReset();
    upsert.mockClear();
    remove.mockClear();
  });

  it('lists policies on mount', async () => {
    list.mockResolvedValue({ policies: [samplePolicy] });
    const wrapper = mount(PolicyEditor);
    await flushPromises();
    expect(list).toHaveBeenCalled();
    expect(wrapper.find('[data-policy-id="pol-111"]').exists()).toBe(true);
    // Effect/kind/scope labels are rendered via i18n.
    expect(wrapper.text()).toContain('Deny');
    expect(wrapper.text()).toContain('Cost budget');
  });

  it('renders an empty state with no policies', async () => {
    list.mockResolvedValue({ policies: [] });
    const wrapper = mount(PolicyEditor);
    await flushPromises();
    expect(wrapper.text()).toContain('No policies configured yet.');
  });

  it('upserts on save and re-fetches the list', async () => {
    list.mockResolvedValue({ policies: [] });
    const wrapper = mount(PolicyEditor);
    await flushPromises();
    list.mockClear();

    await (wrapper.vm as unknown as { save: () => Promise<void> }).save();
    await flushPromises();

    expect(upsert).toHaveBeenCalledTimes(1);
    const arg = upsert.mock.calls[0][0] as Record<string, unknown>;
    expect(arg.scope).toBe('session');
    expect(arg.kind).toBe('cost_budget');
    expect(arg.effect).toBe('ask');
    // refreshed after save.
    expect(list).toHaveBeenCalled();
  });

  it('removes a policy', async () => {
    list.mockResolvedValue({ policies: [samplePolicy] });
    const wrapper = mount(PolicyEditor);
    await flushPromises();

    await (wrapper.vm as unknown as { remove: (id: string) => Promise<void> }).remove('pol-111');
    await flushPromises();
    expect(remove).toHaveBeenCalledWith('pol-111');
  });
});
