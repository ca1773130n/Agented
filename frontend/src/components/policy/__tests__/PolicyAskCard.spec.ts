import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import PolicyAskCard from '../PolicyAskCard.vue';

const decide = vi.fn((..._args: unknown[]) => Promise.resolve({ ok: true }));

vi.mock('../../../services/api', () => ({
  policyApi: {
    decide: (...args: unknown[]) => decide(...args),
    list: vi.fn(),
    upsert: vi.fn(),
    remove: vi.fn(),
  },
}));

const event = {
  policy_id: 'pol-abc',
  kind: 'ask_on_os_tools',
  reason: 'OS tool requires approval: shell',
  scope: 'session' as const,
};

function btn(wrapper: ReturnType<typeof mount>, label: string) {
  return wrapper.findAll('button').find((b) => b.text() === label)!;
}

describe('PolicyAskCard', () => {
  beforeEach(() => decide.mockClear());

  it('renders the ask reason and scope', () => {
    const wrapper = mount(PolicyAskCard, { props: { event, sessionId: 'sess-1' } });
    expect(wrapper.text()).toContain(event.reason);
    expect(wrapper.text().toLowerCase()).toContain('session');
  });

  it('calls decide(sessionId, "approve") on Approve and emits resolved', async () => {
    const wrapper = mount(PolicyAskCard, { props: { event, sessionId: 'sess-1' } });
    await btn(wrapper, 'Approve').trigger('click');
    await flushPromises();
    expect(decide).toHaveBeenCalledWith('sess-1', 'approve');
    expect(wrapper.emitted('resolved')?.[0]).toEqual(['approve']);
  });

  it('calls decide(sessionId, "deny") on Deny', async () => {
    const wrapper = mount(PolicyAskCard, { props: { event, sessionId: 'sess-2' } });
    await btn(wrapper, 'Deny').trigger('click');
    await flushPromises();
    expect(decide).toHaveBeenCalledWith('sess-2', 'deny');
    expect(wrapper.emitted('resolved')?.[0]).toEqual(['deny']);
  });

  it('does not re-submit once resolved', async () => {
    const wrapper = mount(PolicyAskCard, { props: { event, sessionId: 'sess-3' } });
    await btn(wrapper, 'Approve').trigger('click');
    await flushPromises();
    // After resolution the action buttons are gone (resolved view shown).
    expect(wrapper.findAll('button').length).toBe(0);
    expect(decide).toHaveBeenCalledTimes(1);
  });
});
