/**
 * Phase 19 (REQ-13) component tests:
 *   - SuperAgentDriverSelector defaults to 'grd', renders all three
 *     options, and emits update:modelValue on change.
 *   - ProjectTeamLeaderChat renders the GRD-session link when a
 *     grd-driver turn surfaces a session id on the finish delta.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import SuperAgentDriverSelector from '../../super-agents/SuperAgentDriverSelector.vue';
import ProjectTeamLeaderChat from '../ProjectTeamLeaderChat.vue';

// ---------------------------------------------------------------------------
// i18n — only the driver.* (+ minimal chat) namespaces under test.
// ---------------------------------------------------------------------------
const driverMessages = {
  selectorTitle: 'Execution driver',
  projectTitle: 'Execution Driver',
  projectDescription: 'Choose a driver.',
  saLabel: 'Driver',
  changeHint: 'Driver change will apply on save.',
  saved: 'Driver updated.',
  viewGrdSession: 'View GRD session',
  options: { grd: 'GRD (default)', cli_agent: 'CLI Agent', cliproxy: 'CLIProxy' },
};

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: {
      en: {
        driver: driverMessages,
        projectTeamLeaderChat: {
          thinkingLabel: 'Thinking',
          toolsLabel: '{count} tool execution(s)',
          queuedNotice: 'Queued. {detail}',
          retrying: 'Retrying…',
          rotatedNotice: 'Rotated {from} → {to}',
          allRateLimited: 'All rate-limited. {detail}',
          streamError: 'Stream error.',
          title: 'Leader Chat',
          groundedBadge: 'grounded',
          conversationWith: 'Conversation with',
          resolving: 'Resolving…',
          persistsNote: 'Persists',
          openingSession: 'Opening…',
          openFailed: 'Open failed',
          sendFailed: 'Send failed',
          emptyHint: 'Ask anything',
          queriedLabel: 'Queried:',
          citedLabel: 'Cited:',
          citationKind: 'Citation kind: {kind}',
          inputPlaceholder: 'Ask…',
          askButton: 'Ask',
          planningProgress: 'Planning retrieval…',
          retrievalProgress: 'Retrieved {chunks} chunks ({iterations} iter)',
        },
      },
    },
  });
}

// ===========================================================================
// SuperAgentDriverSelector
// ===========================================================================
describe('SuperAgentDriverSelector', () => {
  it('defaults to grd and renders all three options', () => {
    const wrapper = mount(SuperAgentDriverSelector, {
      global: { plugins: [makeI18n()] },
    });
    const select = wrapper.get('[data-testid="driver-selector"]');
    // default value
    expect((select.element as HTMLSelectElement).value).toBe('grd');
    // all three options present
    const drivers = wrapper.findAll('option').map((o) => o.attributes('data-driver'));
    expect(drivers).toContain('grd');
    expect(drivers).toContain('cli_agent');
    expect(drivers).toContain('cliproxy');
    expect(drivers).toHaveLength(3);
  });

  it('emits update:modelValue with the chosen driver on change', async () => {
    const wrapper = mount(SuperAgentDriverSelector, {
      global: { plugins: [makeI18n()] },
      props: { modelValue: 'grd' as const },
    });
    const select = wrapper.get('[data-testid="driver-selector"]');
    await select.setValue('cli_agent');
    const emitted = wrapper.emitted('update:modelValue');
    expect(emitted).toBeTruthy();
    expect(emitted![0]).toEqual(['cli_agent']);
  });

  it('falls back to grd when modelValue is null (inherit)', () => {
    const wrapper = mount(SuperAgentDriverSelector, {
      global: { plugins: [makeI18n()] },
      props: { modelValue: null },
    });
    const select = wrapper.get('[data-testid="driver-selector"]');
    expect((select.element as HTMLSelectElement).value).toBe('grd');
  });
});

// ===========================================================================
// ProjectTeamLeaderChat — GRD-session linkage
// ===========================================================================
vi.mock('../../../services/api/team-leader-chat', () => ({
  teamLeaderChatApi: { openSession: vi.fn() },
}));
vi.mock('../../../services/api/super-agents', () => ({
  superAgentSessionApi: { chatStream: vi.fn() },
}));

import { teamLeaderChatApi } from '../../../services/api/team-leader-chat';
import { superAgentSessionApi } from '../../../services/api/super-agents';

interface FakeES {
  listeners: Record<string, Array<(ev: { data: string }) => void>>;
  onerror: (() => void) | null;
  addEventListener(event: string, handler: (ev: { data: string }) => void): void;
  close(): void;
  fire(event: string, data: object): void;
}

function makeFakeES(): FakeES {
  return {
    listeners: {},
    onerror: null,
    addEventListener(event, handler) {
      (this.listeners[event] ||= []).push(handler);
    },
    close() {},
    fire(event, data) {
      for (const h of this.listeners[event] || []) h({ data: JSON.stringify(data) });
    },
  };
}

const FAKE_SESSION = {
  project_id: 'proj-x',
  super_agent_id: 'psa-abc',
  session_id: 'sess-123',
  leader_template_id: 'tpl-1',
  leader_name: 'Leader',
  tesserae_enabled: false,
};

// RouterLink stub — renders its slot + exposes the resolved `to` for asserts.
const RouterLinkStub = {
  name: 'RouterLink',
  props: ['to'],
  template: '<a class="router-link-stub" :data-to="JSON.stringify(to)"><slot /></a>',
};

function mountChat() {
  const fakeES = makeFakeES();
  vi.mocked(teamLeaderChatApi.openSession).mockResolvedValue(FAKE_SESSION as never);
  vi.mocked(superAgentSessionApi.chatStream).mockReturnValue(fakeES as never);
  const wrapper = mount(ProjectTeamLeaderChat, {
    global: {
      plugins: [makeI18n()],
      stubs: { RouterLink: RouterLinkStub },
    },
    props: { projectId: 'proj-x' },
  });
  return { wrapper, fakeES };
}

describe('ProjectTeamLeaderChat — GRD session linkage', () => {
  let wrappers: Array<{ unmount: () => void }> = [];

  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('renders a View GRD session link when a grd-driver turn carries a session id', async () => {
    const { wrapper, fakeES } = mountChat();
    wrappers.push(wrapper);
    await flushPromises();

    fakeES.fire('state_delta', { type: 'content_delta', data: { content: 'Ran on GRD.' } });
    fakeES.fire('state_delta', {
      type: 'finish',
      data: { finish_reason: 'complete', grd_session_id: 'psess-9xyz' },
    });
    await flushPromises();

    const link = wrapper.find('[data-testid="grd-session-link"]');
    expect(link.exists()).toBe(true);
    expect(link.text()).toContain('View GRD session');
    expect(link.attributes('data-session-id')).toBe('psess-9xyz');
    // link targets the project-management session view for that psess id
    const to = JSON.parse(link.attributes('data-to') || '{}');
    expect(to.name).toBe('project-management');
    expect(to.query.session).toBe('psess-9xyz');
  });

  it('does NOT render the GRD link for a non-grd turn (no session id on finish)', async () => {
    const { wrapper, fakeES } = mountChat();
    wrappers.push(wrapper);
    await flushPromises();

    fakeES.fire('state_delta', { type: 'content_delta', data: { content: 'Plain reply.' } });
    fakeES.fire('state_delta', { type: 'finish', data: { finish_reason: 'complete' } });
    await flushPromises();

    expect(wrapper.find('[data-testid="grd-session-link"]').exists()).toBe(false);
  });
});
