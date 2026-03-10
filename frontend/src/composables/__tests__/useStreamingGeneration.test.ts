import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks -- declared before composable import (vi.mock hoisting)
// ---------------------------------------------------------------------------

vi.mock('../../services/api', () => ({
  isAbortError: (e: unknown) =>
    e instanceof DOMException && e.name === 'AbortError',
}));

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

import { useStreamingGeneration } from '../useStreamingGeneration';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Encode a string as a Uint8Array for ReadableStream chunks. */
function encode(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

/** Build SSE-formatted text for a single event. */
function sseBlock(eventType: string, data: unknown): string {
  return `event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`;
}

/**
 * Create a mock fetch Response with a ReadableStream body that yields
 * the provided chunks, then signals done.
 */
function mockStreamResponse(chunks: string[], status = 200): Response {
  let idx = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (idx < chunks.length) {
        controller.enqueue(encode(chunks[idx]));
        idx++;
      } else {
        controller.close();
      }
    },
  });

  return {
    ok: status >= 200 && status < 300,
    status,
    body,
    json: () => Promise.resolve({ error: `HTTP ${status}` }),
  } as unknown as Response;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useStreamingGeneration', () => {
  let gen: ReturnType<typeof useStreamingGeneration>;

  beforeEach(() => {
    vi.clearAllMocks();
    gen = useStreamingGeneration();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -----------------------------------------------------------------------
  // Initial state
  // -----------------------------------------------------------------------
  describe('initial state', () => {
    it('has empty log', () => {
      expect(gen.log.value).toEqual([]);
    });

    it('has empty phase', () => {
      expect(gen.phase.value).toBe('');
    });

    it('is not streaming', () => {
      expect(gen.isStreaming.value).toBe(false);
    });
  });

  // -----------------------------------------------------------------------
  // startStream -- success path
  // -----------------------------------------------------------------------
  describe('startStream success', () => {
    it('processes phase, thinking, output, and result events', async () => {
      const chunks = [
        sseBlock('phase', { message: 'Analyzing...' }),
        sseBlock('thinking', { content: 'Let me think...' }),
        sseBlock('output', { content: 'Generated code' }),
        sseBlock('result', { answer: 42 }),
      ];

      vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockStreamResponse(chunks));

      const result = await gen.startStream<{ answer: number }>('/api/generate', { prompt: 'test' });

      expect(result).toEqual({ answer: 42 });
      expect(gen.phase.value).toBe('Analyzing...');
      expect(gen.log.value).toEqual([
        { type: 'phase', text: 'Analyzing...' },
        { type: 'thinking', text: 'Let me think...' },
        { type: 'output', text: 'Generated code' },
        { type: 'phase', text: 'Complete!' },
      ]);
      expect(gen.isStreaming.value).toBe(false);
    });

    it('resets isStreaming to false after stream completes', async () => {
      const chunks = [sseBlock('phase', { message: 'Done' })];
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockStreamResponse(chunks));

      await gen.startStream('/api/gen', {});

      expect(gen.isStreaming.value).toBe(false);
    });
  });

  // -----------------------------------------------------------------------
  // startStream -- error paths
  // -----------------------------------------------------------------------
  describe('startStream error paths', () => {
    it('returns null and logs error on non-ok response', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ error: 'Internal server error' }),
      } as unknown as Response);

      const result = await gen.startStream('/api/gen', {});

      expect(result).toBeNull();
      expect(gen.log.value).toEqual([{ type: 'error', text: 'Internal server error' }]);
    });

    it('handles non-ok response with unparseable JSON body', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: false,
        status: 502,
        json: () => Promise.reject(new Error('not json')),
      } as unknown as Response);

      const result = await gen.startStream('/api/gen', {});

      expect(result).toBeNull();
      expect(gen.log.value[0].text).toBe('Unknown error');
    });

    it('returns null and logs error when body is null', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        status: 200,
        body: null,
      } as unknown as Response);

      const result = await gen.startStream('/api/gen', {});

      expect(result).toBeNull();
      expect(gen.log.value).toEqual([{ type: 'error', text: 'Streaming not supported' }]);
    });

    it('returns null on network failure', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));

      const result = await gen.startStream('/api/gen', {});

      expect(result).toBeNull();
      expect(gen.log.value).toEqual([{ type: 'error', text: 'Connection failed' }]);
    });

    it('returns null silently on abort', async () => {
      const abortErr = new DOMException('Aborted', 'AbortError');
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(abortErr);

      const result = await gen.startStream('/api/gen', {});

      expect(result).toBeNull();
      // No error log for abort
      expect(gen.log.value).toEqual([]);
    });

    it('handles SSE error event type', async () => {
      const chunks = [sseBlock('error', { error: 'Generation failed' })];
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockStreamResponse(chunks));

      const result = await gen.startStream('/api/gen', {});

      expect(result).toBeNull();
      expect(gen.log.value).toContainEqual({ type: 'error', text: 'Generation failed' });
    });

    it('ignores malformed JSON in SSE data', async () => {
      const chunks = ['event: phase\ndata: {invalid json\n\n'];
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockStreamResponse(chunks));

      const result = await gen.startStream('/api/gen', {});

      // Should not throw, just return null (no result event)
      expect(result).toBeNull();
      expect(gen.log.value).toEqual([]);
    });
  });

  // -----------------------------------------------------------------------
  // reset
  // -----------------------------------------------------------------------
  describe('reset', () => {
    it('clears log, phase, and streaming state', () => {
      gen.log.value = [{ type: 'phase', text: 'old' }];
      gen.phase.value = 'running';
      gen.isStreaming.value = true;

      gen.reset();

      expect(gen.log.value).toEqual([]);
      expect(gen.phase.value).toBe('');
      expect(gen.isStreaming.value).toBe(false);
    });
  });

  // -----------------------------------------------------------------------
  // Cancellation -- new stream aborts previous
  // -----------------------------------------------------------------------
  describe('cancellation', () => {
    it('calling reset clears accumulated state', async () => {
      const chunks = [
        sseBlock('phase', { message: 'Working...' }),
        sseBlock('output', { content: 'Some output' }),
      ];
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(mockStreamResponse(chunks));

      await gen.startStream('/api/gen', {});

      expect(gen.log.value.length).toBeGreaterThan(0);
      expect(gen.phase.value).toBe('Working...');

      gen.reset();

      expect(gen.log.value).toEqual([]);
      expect(gen.phase.value).toBe('');
      expect(gen.isStreaming.value).toBe(false);
    });
  });
});
