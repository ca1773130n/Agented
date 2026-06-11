/**
 * TDD tests for RAG delta handling in ProjectTeamLeaderChat.vue:
 *   - planning / retrieval render as progress lines
 *   - citations delta attaches to last assistant message + replaces regex
 *   - unknown delta is safe (no crash)
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import ProjectTeamLeaderChat from '../ProjectTeamLeaderChat.vue';

// ---------------------------------------------------------------------------
// Mock the two modules the component uses for session setup and streaming
// ---------------------------------------------------------------------------
vi.mock('../../../services/api/team-leader-chat', () => ({
  teamLeaderChatApi: {
    openSession: vi.fn(),
  },
}));

vi.mock('../../../services/api/super-agents', () => ({
  superAgentSessionApi: {
    chatStream: vi.fn(),
  },
}));

import { teamLeaderChatApi } from '../../../services/api/team-leader-chat';
import { superAgentSessionApi } from '../../../services/api/super-agents';

// ---------------------------------------------------------------------------
// Minimal i18n setup
// ---------------------------------------------------------------------------
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
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

// ---------------------------------------------------------------------------
// Fake EventSource helper — fires events synchronously
// ---------------------------------------------------------------------------

interface FakeES {
  listeners: Record<string, Array<(ev: { data: string }) => void>>;
  onerror: (() => void) | null;
  addEventListener(event: string, handler: (ev: { data: string }) => void): void;
  close(): void;
  fire(event: string, data: object): void;
}

function makeFakeES(): FakeES {
  const es: FakeES = {
    listeners: {},
    onerror: null,
    addEventListener(event, handler) {
      if (!this.listeners[event]) this.listeners[event] = [];
      this.listeners[event].push(handler);
    },
    close() {},
    fire(event, data) {
      for (const h of this.listeners[event] || []) {
        h({ data: JSON.stringify(data) });
      }
    },
  };
  return es;
}

// ---------------------------------------------------------------------------
// Fake session returned by teamLeaderChatApi.openSession
// ---------------------------------------------------------------------------

const FAKE_SESSION = {
  project_id: 'proj-x',
  super_agent_id: 'psa-abc',
  session_id: 'sess-123',
  leader_template_id: 'tpl-1',
  leader_name: 'Leader',
  tesserae_enabled: false,
};

// ---------------------------------------------------------------------------
// Mount helper
// ---------------------------------------------------------------------------

function mountChat() {
  const fakeES = makeFakeES();

  vi.mocked(teamLeaderChatApi.openSession).mockResolvedValue(FAKE_SESSION as never);
  vi.mocked(superAgentSessionApi.chatStream).mockReturnValue(fakeES as never);

  const wrapper = mount(ProjectTeamLeaderChat, {
    global: { plugins: [i18n] },
    props: { projectId: 'proj-x' },
  });

  return { wrapper, fakeES };
}

// ---------------------------------------------------------------------------

describe('ProjectTeamLeaderChat — RAG deltas', () => {
  let wrappers: Array<{ unmount: () => void }> = [];

  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  // --------------------------------------------------------------------------
  it('renders planning progress line when planning delta arrives', async () => {
    const { wrapper, fakeES } = mountChat();
    wrappers.push(wrapper);
    await flushPromises();

    fakeES.fire('state_delta', { type: 'planning', data: { status: 'started' } });
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain('Planning');
  });

  // --------------------------------------------------------------------------
  it('renders retrieval progress line with chunk/iteration info', async () => {
    const { wrapper, fakeES } = mountChat();
    wrappers.push(wrapper);
    await flushPromises();

    fakeES.fire('state_delta', { type: 'retrieval', data: { chunks: 5, iterations: 2, sufficient: true } });
    await flushPromises();

    const text = wrapper.text();
    expect(text).toContain('5');
  });

  // --------------------------------------------------------------------------
  it('citations delta attaches pre-mapped citations to last assistant message, replacing regex', async () => {
    const { wrapper, fakeES } = mountChat();
    wrappers.push(wrapper);
    await flushPromises();

    // Simulate an assistant turn that the regex WOULD derive `main.py` from
    fakeES.fire('state_delta', { type: 'content_delta', data: { content: 'Answer referencing `main.py`' } });
    fakeES.fire('state_delta', { type: 'finish', data: {} });
    await flushPromises();

    // Now a RAG citations delta arrives with explicit backend-provided citations
    fakeES.fire('state_delta', {
      type: 'citations',
      data: {
        message_scope: 'last_assistant',
        citations: [
          { kind: 'kg_entity', value: 'kge-1234' },
          { kind: 'takeaway', value: 'tk_abc123' },
        ],
        facts: [{ claim: 'foo', evidence: [], confidence: 0.9 }],
      },
    });
    await flushPromises();

    const chips = wrapper.findAll('.cite-chip');
    const values = chips.map((c) => c.text());
    expect(values).toContain('kge-1234');
    expect(values).toContain('tk_abc123');
    // regex-derived `main.py` should be gone (replaced by the RAG citations)
    expect(values).not.toContain('main.py');
  });

  // --------------------------------------------------------------------------
  it('citations delta on empty messages list does not throw', async () => {
    const { wrapper, fakeES } = mountChat();
    wrappers.push(wrapper);
    await flushPromises();

    expect(() => {
      fakeES.fire('state_delta', {
        type: 'citations',
        data: {
          message_scope: 'last_assistant',
          citations: [{ kind: 'file', value: 'a.ts' }],
          facts: [],
        },
      });
    }).not.toThrow();
  });

  // --------------------------------------------------------------------------
  it('unknown delta type does not crash', async () => {
    const { wrapper, fakeES } = mountChat();
    wrappers.push(wrapper);
    await flushPromises();

    expect(() => {
      fakeES.fire('state_delta', { type: 'future_unknown_type', data: { stuff: 42 } });
    }).not.toThrow();
  });
});
