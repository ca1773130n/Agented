/**
 * Phase 23 (finding 7) — policy_ask SSE wiring.
 *
 * Proves the live wiring added to useProjectSession + ProjectSessionPanel: a
 * `policy_ask` SSE event flows through the composable's event handler into the
 * registered `onPolicyAsk` callback, which renders a PolicyAskCard; clicking
 * Approve POSTs the decision via policyApi.decide. A `policy_ask_resolved` event
 * clears the card.
 *
 * We mock useEventSource to CAPTURE the events map the composable registers, then
 * invoke the `policy_ask` handler directly — exercising the real composable code
 * path without a live EventSource.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref, defineComponent, nextTick } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';
import PolicyAskCard from '../../components/policy/PolicyAskCard.vue';
import type { PolicyAskEvent } from '../../services/api';

// Capture the SSE events map registered by useProjectSession.
let capturedEvents: Record<string, (e: MessageEvent) => void> = {};

vi.mock('../useEventSource', () => ({
  useEventSource: (opts: { events: Record<string, (e: MessageEvent) => void> }) => {
    capturedEvents = opts.events;
    return {
      connect: vi.fn(),
      close: vi.fn(),
      getSource: vi.fn().mockReturnValue(null),
      status: ref('idle'),
    };
  },
}));

vi.mock('../../services/api/grd', () => ({
  grdApi: {
    streamSession: vi.fn(),
    listSessions: vi.fn(),
    createSession: vi.fn(),
    createRalphSession: vi.fn(),
    createTeamSession: vi.fn(),
    sendInput: vi.fn(),
    stopSession: vi.fn(),
    pauseSession: vi.fn(),
    resumeSession: vi.fn(),
  },
}));

const decide = vi.fn((..._args: unknown[]) => Promise.resolve({ ok: true }));
vi.mock('../../services/api', () => ({
  policyApi: {
    decide: (...args: unknown[]) => decide(...args),
    list: vi.fn(),
    upsert: vi.fn(),
    remove: vi.fn(),
  },
}));

import { useProjectSession } from '../useProjectSession';

// A minimal harness mirroring the ProjectSessionPanel wiring: register the
// policy-ask callbacks, store the pending event, and render PolicyAskCard.
const Harness = defineComponent({
  components: { PolicyAskCard },
  setup() {
    const projectId = ref('proj-x');
    const session = useProjectSession(projectId);
    const pending = ref<PolicyAskEvent | null>(null);
    session.onPolicyAsk((e) => {
      pending.value = e;
    });
    session.onPolicyAskResolved(() => {
      pending.value = null;
    });
    return { pending };
  },
  template:
    '<PolicyAskCard v-if="pending" :event="pending" session-id="sess-1" @resolved="pending = null" />',
});

const askPayload = {
  ask_id: 'ask-xyz',
  policy_id: 'pol-abc',
  kind: 'ask_on_os_tools',
  reason: 'OS tool requires approval: shell',
  scope: 'session',
};

describe('policy_ask SSE wiring', () => {
  beforeEach(() => {
    capturedEvents = {};
    decide.mockClear();
  });

  it('renders PolicyAskCard on a policy_ask event and POSTs the decision', async () => {
    const wrapper = mount(Harness);
    // No card before the event.
    expect(wrapper.findComponent(PolicyAskCard).exists()).toBe(false);
    expect(capturedEvents.policy_ask).toBeTypeOf('function');

    // Fire the SSE event through the real composable handler.
    capturedEvents.policy_ask({ data: JSON.stringify(askPayload) } as MessageEvent);
    await nextTick();

    const card = wrapper.findComponent(PolicyAskCard);
    expect(card.exists()).toBe(true);
    expect(wrapper.text()).toContain(askPayload.reason);

    // Approve → decision POSTed for the session.
    const approve = wrapper.findAll('button').find((b) => b.text() === 'Approve')!;
    await approve.trigger('click');
    await flushPromises();
    expect(decide).toHaveBeenCalledWith('sess-1', 'ask-xyz', 'approve');

    // Resolution clears the card.
    await nextTick();
    expect(wrapper.findComponent(PolicyAskCard).exists()).toBe(false);
  });

  it('clears the card on a policy_ask_resolved event', async () => {
    const wrapper = mount(Harness);
    capturedEvents.policy_ask({ data: JSON.stringify(askPayload) } as MessageEvent);
    await nextTick();
    expect(wrapper.findComponent(PolicyAskCard).exists()).toBe(true);

    capturedEvents.policy_ask_resolved({ data: '{}' } as MessageEvent);
    await nextTick();
    expect(wrapper.findComponent(PolicyAskCard).exists()).toBe(false);
  });
});
