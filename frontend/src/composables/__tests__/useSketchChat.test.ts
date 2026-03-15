import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks -- declared before composable import (vi.mock hoisting)
// ---------------------------------------------------------------------------

const mockSketchApiList = vi.fn();
const mockSketchApiGet = vi.fn();
const mockSketchApiCreate = vi.fn();
const mockSketchApiClassify = vi.fn();
const mockSketchApiRoute = vi.fn();
const mockProjectApiList = vi.fn();

vi.mock('../../services/api', () => ({
  sketchApi: {
    list: (...a: unknown[]) => mockSketchApiList(...a),
    get: (...a: unknown[]) => mockSketchApiGet(...a),
    create: (...a: unknown[]) => mockSketchApiCreate(...a),
    classify: (...a: unknown[]) => mockSketchApiClassify(...a),
    route: (...a: unknown[]) => mockSketchApiRoute(...a),
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useSketchChat', () => {
  let chat: ReturnType<typeof useSketchChat>;

  beforeEach(() => {
    vi.clearAllMocks();
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
    it('creates, classifies, and fetches sketch on success', async () => {
      mockSketchApiCreate.mockResolvedValue({ sketch_id: 'sk-new' });
      mockSketchApiClassify.mockResolvedValue({});
      mockSketchApiGet.mockResolvedValue({
        id: 'sk-new',
        title: 'test',
        classification_json: JSON.stringify({
          phase: 'design',
          domains: ['ui'],
          complexity: 'low',
          confidence: 0.95,
        }),
      });
      mockSketchApiList.mockResolvedValue({ sketches: [] });

      await chat.submitSketch('Build a button');

      // User message added
      expect(chat.messages.value[0].role).toBe('user');
      expect(chat.messages.value[0].content).toBe('Build a button');

      // Assistant message with classification
      expect(chat.messages.value[1].role).toBe('assistant');
      expect(chat.messages.value[1].content).toContain('Phase: design');
      expect(chat.messages.value[1].content).toContain('Domains: ui');
      expect(chat.messages.value[1].content).toContain('Confidence: 95%');

      expect(chat.currentSketch.value).toBeTruthy();
      expect(chat.isProcessing.value).toBe(false);
    });

    it('uses fallback message when no classification data', async () => {
      mockSketchApiCreate.mockResolvedValue({ sketch_id: 'sk-2' });
      mockSketchApiClassify.mockResolvedValue({});
      mockSketchApiGet.mockResolvedValue({ id: 'sk-2', title: 'test' });
      mockSketchApiList.mockResolvedValue({ sketches: [] });

      await chat.submitSketch('Hello');

      const assistantMsg = chat.messages.value.find((m) => m.role === 'assistant');
      expect(assistantMsg?.content).toBe('Sketch created and classified.');
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

      expect(chat.currentSketch.value?.id).toBe('sk-1');
      expect(chat.messages.value[0].role).toBe('user');
      expect(chat.messages.value[0].content).toBe('Full content here');
      expect(chat.messages.value[1].role).toBe('assistant');
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
