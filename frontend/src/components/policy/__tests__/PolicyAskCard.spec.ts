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
  ask_id: 'ask-xyz',
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

  it('calls decide(sessionId, askId, "approve") on Approve and emits resolved', async () => {
    const wrapper = mount(PolicyAskCard, { props: { event, sessionId: 'sess-1' } });
    await btn(wrapper, 'Approve').trigger('click');
    await flushPromises();
    expect(decide).toHaveBeenCalledWith('sess-1', 'ask-xyz', 'approve');
    expect(wrapper.emitted('resolved')?.[0]).toEqual(['approve']);
  });

  it('calls decide(sessionId, askId, "deny") on Deny', async () => {
    const wrapper = mount(PolicyAskCard, { props: { event, sessionId: 'sess-2' } });
    await btn(wrapper, 'Deny').trigger('click');
    await flushPromises();
    expect(decide).toHaveBeenCalledWith('sess-2', 'ask-xyz', 'deny');
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

  it('surfaces a stale state instead of false success on ok:false (MINOR 8)', async () => {
    // Backend reports no pending ASK was resolved (already resolved / timed out).
    decide.mockResolvedValueOnce({ ok: false });
    const wrapper = mount(PolicyAskCard, { props: { event, sessionId: 'sess-stale' } });
    await btn(wrapper, 'Approve').trigger('click');
    await flushPromises();

    expect(decide).toHaveBeenCalledWith('sess-stale', 'ask-xyz', 'approve');
    // No false success: 'resolved' is NOT emitted and the resolved view is hidden.
    expect(wrapper.emitted('resolved')).toBeFalsy();
    // The stale notice is shown and the action buttons are gone.
    expect(wrapper.text().toLowerCase()).toContain('already resolved');
    expect(wrapper.findAll('button').length).toBe(0);
  });
});
