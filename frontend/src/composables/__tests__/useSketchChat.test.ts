import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks -- declared before composable import (vi.mock hoisting)
// ---------------------------------------------------------------------------

const mockSketchApiList = vi.fn();
const mockSketchApiGet = vi.fn();
const mockSketchApiCreate = vi.fn();
const mockSketchApiClassify = vi.fn();
const mockSketchApiRoute = vi.fn();
const mockSketchApiUpdate = vi.fn();
const mockSketchApiIdeate = vi.fn();
const mockProjectApiList = vi.fn();

vi.mock('../../services/api', () => ({
  sketchApi: {
    list: (...a: unknown[]) => mockSketchApiList(...a),
    get: (...a: unknown[]) => mockSketchApiGet(...a),
    create: (...a: unknown[]) => mockSketchApiCreate(...a),
    classify: (...a: unknown[]) => mockSketchApiClassify(...a),
    route: (...a: unknown[]) => mockSketchApiRoute(...a),
    update: (...a: unknown[]) => mockSketchApiUpdate(...a),
    getDelegations: vi.fn().mockResolvedValue({ delegations: [] }),
    // Ideation stream: invoke the handlers synchronously so the awaited
    // submitSketch resolves with a streamed assistant reply.
    ideateStream: async (
      msgs: unknown,
      handlers: {
        onRetrieval?: (p: import('../../services/api').RetrievalDetails) => void;
        onContent?: (c: string) => void;
        onDone?: () => void;
      },
    ) => {
      mockSketchApiIdeate(msgs);
      handlers?.onRetrieval?.({
        scope: 'federated',
        projects: ['a', 'b'],
        citations: 3,
        stats: {
          nodes: 100,
          edges: 200,
          semantic_backend: 'hash-bucket',
          semantic_skipped: 'no real embedding backend',
          semantic_added: 0,
        },
        sources: [{ name: 'file.py', path: 'file.py', wiki_kind: null, project: 'a' }],
        federation: { per_project_nodes: { a: 100, b: 20 }, identity_merges: 0 },
      });
      handlers?.onContent?.('partner reply');
      handlers?.onDone?.();
    },
  },
  projectApi: {
    list: (...a: unknown[]) => mockProjectApiList(...a),
  },
  superAgentSessionApi: {
    chatStream: vi.fn(),
  },
  isAbortError: (e: unknown) =>
    e instanceof DOMException && e.name === 'AbortError',
}));

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

import { useSketchChat } from '../useSketchChat';
import { superAgentSessionApi } from '../../services/api';

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useSketchChat', () => {
  let chat: ReturnType<typeof useSketchChat>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockSketchApiUpdate.mockResolvedValue({}); // transcript-persist before routing
    chat = useSketchChat();
  });

  // -----------------------------------------------------------------------
  // Initial state
  // -----------------------------------------------------------------------
  describe('initial state', () => {
    it('has empty sketches list', () => {
      expect(chat.sketches.value).toEqual([]);
    });

    it('has no current sketch', () => {
      expect(chat.currentSketch.value).toBeNull();
    });

    it('has no error', () => {
      expect(chat.error.value).toBeNull();
    });

    it('is not processing', () => {
      expect(chat.isProcessing.value).toBe(false);
    });

    it('has empty messages', () => {
      expect(chat.messages.value).toEqual([]);
    });
  });

  // -----------------------------------------------------------------------
  // loadProjects
  // -----------------------------------------------------------------------
  describe('loadProjects', () => {
    it('loads projects on success', async () => {
      const projects = [{ id: 'proj-1', name: 'P1' }];
      mockProjectApiList.mockResolvedValue({ projects });

      await chat.loadProjects();

      expect(chat.projects.value).toEqual(projects);
    });

    it('sets error on failure', async () => {
      mockProjectApiList.mockRejectedValue(new Error('Network error'));

      await chat.loadProjects();

      expect(chat.error.value).toBe('Network error');
    });

    it('sets generic error for non-Error throws', async () => {
      mockProjectApiList.mockRejectedValue('boom');

      await chat.loadProjects();

      expect(chat.error.value).toBe('Failed to load projects');
    });
  });

  // -----------------------------------------------------------------------
  // loadSketches
  // -----------------------------------------------------------------------
  describe('loadSketches', () => {
    it('loads sketches without filter when no project selected', async () => {
      mockSketchApiList.mockResolvedValue({ sketches: [{ id: 'sk-1' }] });

      await chat.loadSketches();

      expect(mockSketchApiList).toHaveBeenCalledWith({});
      expect(chat.sketches.value).toEqual([{ id: 'sk-1' }]);
    });

    it('passes project_id filter when project is selected', async () => {
      chat.selectedProjectId.value = 'proj-abc';
      mockSketchApiList.mockResolvedValue({ sketches: [] });

      await chat.loadSketches();

      expect(mockSketchApiList).toHaveBeenCalledWith({ project_id: 'proj-abc' });
    });

    it('sets error on failure', async () => {
      mockSketchApiList.mockRejectedValue(new Error('Server error'));

      await chat.loadSketches();

      expect(chat.error.value).toBe('Server error');
    });
  });

  // -----------------------------------------------------------------------
  // submitSketch
  // -----------------------------------------------------------------------
  describe('submitSketch', () => {
    it('creates + classifies ONCE, then streams a grounded ideation reply (no auto-route)', async () => {
      mockSketchApiCreate.mockResolvedValue({ sketch_id: 'sk-new' });
      mockSketchApiClassify.mockResolvedValue({});
      mockSketchApiGet.mockResolvedValue({ id: 'sk-new', title: 'test', status: 'classified' });
      mockSketchApiList.mockResolvedValue({ sketches: [] });

      await chat.submitSketch('Build a button');

      // User message + a streamed assistant ideation reply.
      expect(chat.messages.value[0].role).toBe('user');
      expect(chat.messages.value[0].content).toBe('Build a button');
      const assistant = chat.messages.value.find((m) => m.role === 'assistant');
      expect(assistant?.content).toBe('partner reply');
      // The streamed turn lives in EXACTLY one place: committed to messages, and
      // the live streaming buffer is cleared — otherwise the panel (which renders
      // both) shows the reply in two duplicate bubbles.
      expect(chat.messages.value.filter((m) => m.role === 'assistant')).toHaveLength(1);
      expect(chat.streamingContent.value).toBe('');

      expect(chat.currentSketch.value).toBeTruthy();
      // Ideation ran; routing did NOT (manual button only).
      expect(mockSketchApiIdeate).toHaveBeenCalled();
      expect(mockSketchApiRoute).not.toHaveBeenCalled();
      // Federated grounding provenance surfaced.
      // Full retrieval provenance surfaced (scope + semantic backend + sources).
      expect(chat.grounding.value?.scope).toBe('federated');
      expect(chat.grounding.value?.projects).toEqual(['a', 'b']);
      expect(chat.grounding.value?.citations).toBe(3);
      expect(chat.grounding.value?.stats.semantic_backend).toBe('hash-bucket');
      expect(chat.grounding.value?.sources.map((s) => s.name)).toEqual(['file.py']);
      expect(chat.isProcessing.value).toBe(false);
    });

    it('creates the sketch only ONCE across multiple turns', async () => {
      mockSketchApiCreate.mockResolvedValue({ sketch_id: 'sk-1' });
      mockSketchApiClassify.mockResolvedValue({});
      mockSketchApiGet.mockResolvedValue({ id: 'sk-1', title: 't', status: 'classified' });
      mockSketchApiList.mockResolvedValue({ sketches: [] });

      await chat.submitSketch('first');
      await chat.submitSketch('second');

      expect(mockSketchApiCreate).toHaveBeenCalledTimes(1);
      expect(mockSketchApiIdeate).toHaveBeenCalledTimes(2);
    });

    it('continues the chat even if classify fails (best-effort, no duplicate)', async () => {
      mockSketchApiCreate.mockResolvedValue({ sketch_id: 'sk-x' });
      mockSketchApiClassify.mockRejectedValue(new Error('classify down'));
      mockSketchApiGet.mockResolvedValue({ id: 'sk-x', title: 't', status: 'draft' });
      mockSketchApiList.mockResolvedValue({ sketches: [] });

      await chat.submitSketch('idea');

      expect(mockSketchApiClassify).toHaveBeenCalled(); // classify was attempted...
      expect(chat.currentSketch.value?.id).toBe('sk-x'); // ...and its failure didn't strand the row
      expect(mockSketchApiIdeate).toHaveBeenCalled(); // chat still streamed
      expect(chat.error.value).toBeNull();
    });

    it('sets error and adds error message on API failure', async () => {
      mockSketchApiCreate.mockRejectedValue(new Error('Create failed'));

      await chat.submitSketch('Broken');

      expect(chat.error.value).toBe('Create failed');
      const errMsg = chat.messages.value.find(
        (m) => m.role === 'assistant' && m.content.startsWith('Error:'),
      );
      expect(errMsg).toBeTruthy();
      expect(chat.isProcessing.value).toBe(false);
    });

    it('sets generic error for non-Error throws', async () => {
      mockSketchApiCreate.mockRejectedValue('oops');

      await chat.submitSketch('Broken');

      expect(chat.error.value).toBe('Failed to create or classify sketch');
    });
  });

  // -----------------------------------------------------------------------
  // routeSketch
  // -----------------------------------------------------------------------
  describe('routeSketch', () => {
    it('routes sketch and adds system message with routing info', async () => {
      mockSketchApiRoute.mockResolvedValue({
        routing: { target_type: 'agent', target_id: 'agent-1', reason: 'Best match' },
      });
      mockSketchApiGet.mockResolvedValue({
        id: 'sk-1',
        routing_json: JSON.stringify({
          target_type: 'agent',
          target_id: 'agent-1',
          reason: 'Best match',
        }),
      });
      mockSketchApiList.mockResolvedValue({ sketches: [] });

      await chat.routeSketch('sk-1');

      const msg = chat.messages.value.find((m) => m.role === 'system');
      expect(msg?.content).toContain('agent');
      expect(msg?.content).toContain('agent-1');
      expect(msg?.content).toContain('Best match');
      expect(chat.isProcessing.value).toBe(false);
    });

    it('adds routing message even when routing has no target', async () => {
      mockSketchApiRoute.mockResolvedValue({
        routing: { target_type: 'none', target_id: null, reason: 'No match' },
      });
      mockSketchApiGet.mockResolvedValue({ id: 'sk-1' });
      mockSketchApiList.mockResolvedValue({ sketches: [] });

      await chat.routeSketch('sk-1');

      const msg = chat.messages.value.find((m) => m.role === 'system');
      expect(msg).toBeTruthy();
    });

    it('sets error on route failure', async () => {
      mockSketchApiRoute.mockRejectedValue(new Error('Route failed'));

      await chat.routeSketch('sk-1');

      expect(chat.error.value).toBe('Route failed');
      expect(chat.isProcessing.value).toBe(false);
    });
  });

  // -----------------------------------------------------------------------
  // streaming finish — backend + model labelling
  // -----------------------------------------------------------------------
  describe('streaming finish', () => {
    it('labels the streamed assistant turn with the finish backend + model', async () => {
      vi.useFakeTimers();
      try {
        const listeners: Record<string, (e: MessageEvent) => void> = {};
        const fakeSource = {
          addEventListener: (type: string, cb: (e: MessageEvent) => void) => {
            listeners[type] = cb;
          },
          close: vi.fn(),
          onerror: null as unknown,
        };
        (superAgentSessionApi.chatStream as ReturnType<typeof vi.fn>).mockReturnValue(fakeSource);

        mockSketchApiRoute.mockResolvedValue({
          routing: { target_type: 'agent', target_id: 'agent-1', reason: 'ok' },
          session_id: 'sess-1',
          super_agent_id: 'sa-1',
        });
        mockSketchApiGet.mockResolvedValue({ id: 'sk-1' });
        mockSketchApiList.mockResolvedValue({ sketches: [] });

        await chat.routeSketch('sk-1');

        // Stream a chunk, then finish carrying the resolved backend + model.
        listeners['state_delta']({
          data: JSON.stringify({ type: 'content_delta', content: 'Hi there' }),
        } as MessageEvent);
        listeners['state_delta']({
          data: JSON.stringify({ type: 'finish', data: { backend: 'codex', model: 'gpt-5.1' } }),
        } as MessageEvent);

        const reply = chat.messages.value.find((m) => m.role === 'assistant');
        expect(reply?.content).toBe('Hi there');
        expect(reply?.backend).toBe('codex');
        expect(reply?.model).toBe('gpt-5.1');
      } finally {
        vi.useRealTimers();
      }
    });
  });

  // -----------------------------------------------------------------------
  // selectSketch
  // -----------------------------------------------------------------------
  describe('selectSketch', () => {
    it('rebuilds messages from sketch content and classification', () => {
      chat.selectSketch({
        id: 'sk-1',
        title: 'My Sketch',
        content: 'Full content here',
        classification_json: JSON.stringify({ phase: 'build', complexity: 'high' }),
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
      } as any);

      // The classification + routing summaries are factual metadata
      // (phase, complexity, target SA), not the agent's reply, so they
      // render as ``system`` bubbles. The actual agent response lands
      // as an ``assistant`` bubble after the session-log fetch — that
      // happens asynchronously and isn't observable here without
      // awaiting the call.
      expect(chat.currentSketch.value?.id).toBe('sk-1');
      expect(chat.messages.value[0].role).toBe('user');
      expect(chat.messages.value[0].content).toBe('Full content here');
      expect(chat.messages.value[1].role).toBe('system');
      expect(chat.messages.value[1].content).toContain('Phase: build');
    });

    it('falls back to title when content is empty', () => {
      chat.selectSketch({
        id: 'sk-2',
        title: 'Fallback title',
        content: '',
        created_at: '2026-01-01T00:00:00Z',
      } as any);

      expect(chat.messages.value[0].content).toBe('Fallback title');
    });
  });

  // -----------------------------------------------------------------------
  // clearChat
  // -----------------------------------------------------------------------
  describe('clearChat', () => {
    it('resets current sketch, messages, and error', () => {
      chat.error.value = 'some error';
      chat.messages.value = [{ role: 'user', content: 'hi', timestamp: '' }];
      chat.currentSketch.value = { id: 'sk-1' } as any;

      chat.clearChat();

      expect(chat.currentSketch.value).toBeNull();
      expect(chat.messages.value).toEqual([]);
      expect(chat.error.value).toBeNull();
    });
  });
});
