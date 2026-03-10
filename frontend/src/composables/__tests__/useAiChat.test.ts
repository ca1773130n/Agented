import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ref } from 'vue';

// ---------------------------------------------------------------------------
// Mocks – declared before the composable import so vi.mock hoisting works.
// ---------------------------------------------------------------------------

const mockSuperAgentApiGet = vi.fn();
const mockSessionApiList = vi.fn();
const mockSessionApiCreate = vi.fn();
const mockSessionApiGet = vi.fn();
const mockSessionApiEnd = vi.fn();
const mockSessionApiSendChatMessage = vi.fn();
const mockSessionApiChatStream = vi.fn();

vi.mock('../../services/api', () => ({
  superAgentApi: { get: (...a: unknown[]) => mockSuperAgentApiGet(...a) },
  superAgentSessionApi: {
    list: (...a: unknown[]) => mockSessionApiList(...a),
    create: (...a: unknown[]) => mockSessionApiCreate(...a),
    get: (...a: unknown[]) => mockSessionApiGet(...a),
    end: (...a: unknown[]) => mockSessionApiEnd(...a),
    sendChatMessage: (...a: unknown[]) => mockSessionApiSendChatMessage(...a),
    chatStream: (...a: unknown[]) => mockSessionApiChatStream(...a),
  },
}));

// Mock useEventSource – expose handlers so tests can simulate SSE events.
let capturedEvents: Record<string, (event: MessageEvent) => void> = {};
let capturedOnOpen: (() => void) | undefined;
void capturedOnOpen; // used by mock factory at runtime
const mockSseConnect = vi.fn();
const mockSseClose = vi.fn();
const mockSseGetSource = vi.fn().mockReturnValue(null);

vi.mock('../useEventSource', () => ({
  useEventSource: (opts: {
    events?: Record<string, (event: MessageEvent) => void>;
    onOpen?: () => void;
  }) => {
    capturedEvents = opts.events || {};
    capturedOnOpen = opts.onOpen;
    return { connect: mockSseConnect, close: mockSseClose, getSource: mockSseGetSource };
  },
}));

// Mock Vue's onUnmounted so it doesn't require a component instance.
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

import { useAiChat } from '../useAiChat';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a minimal MessageEvent-like object for SSE handler invocations. */
function sseEvent(data: unknown, lastEventId = '0'): MessageEvent {
  return { data: JSON.stringify(data), lastEventId } as unknown as MessageEvent;
}

/** Fire a state_delta SSE event through the captured handler. */
function fireStateDelta(data: unknown, seq = '0') {
  capturedEvents.state_delta?.(sseEvent(data, seq));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useAiChat', () => {
  let chat: ReturnType<typeof useAiChat>;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    capturedEvents = {};
    capturedOnOpen = undefined;
    chat = useAiChat(ref('sa-abc123'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Initial state
  // -------------------------------------------------------------------------
  describe('initial state', () => {
    it('has empty messages', () => {
      expect(chat.messages.value).toEqual([]);
    });

    it('is not processing', () => {
      expect(chat.isProcessing.value).toBe(false);
    });

    it('has no session', () => {
      expect(chat.sessionId.value).toBeNull();
    });

    it('has no error', () => {
      expect(chat.error.value).toBeNull();
    });

    it('has empty streaming content', () => {
      expect(chat.streamingContent.value).toBe('');
    });

    it('has null superAgent', () => {
      expect(chat.superAgent.value).toBeNull();
    });

    it('has empty sessions list', () => {
      expect(chat.sessions.value).toEqual([]);
    });

    it('defaults to single chat mode', () => {
      expect(chat.chatMode.value).toBe('single');
    });
  });

  // -------------------------------------------------------------------------
  // loadSuperAgent
  // -------------------------------------------------------------------------
  describe('loadSuperAgent', () => {
    it('loads and sets superAgent on success', async () => {
      const agent = { id: 'sa-abc123', name: 'Test Agent' };
      mockSuperAgentApiGet.mockResolvedValue(agent);

      await chat.loadSuperAgent();

      expect(mockSuperAgentApiGet).toHaveBeenCalledWith('sa-abc123');
      expect(chat.superAgent.value).toEqual(agent);
    });

    it('sets error on failure', async () => {
      mockSuperAgentApiGet.mockRejectedValue(new Error('Not found'));

      await chat.loadSuperAgent();

      expect(chat.error.value).toBe('Not found');
    });

    it('sets generic error for non-Error throws', async () => {
      mockSuperAgentApiGet.mockRejectedValue('boom');

      await chat.loadSuperAgent();

      expect(chat.error.value).toBe('Failed to load super agent');
    });
  });

  // -------------------------------------------------------------------------
  // loadSessions
  // -------------------------------------------------------------------------
  describe('loadSessions', () => {
    it('populates sessions list', async () => {
      const sess = [{ id: 'sess-1' }, { id: 'sess-2' }];
      mockSessionApiList.mockResolvedValue({ sessions: sess });

      await chat.loadSessions();

      expect(chat.sessions.value).toEqual(sess);
    });

    it('defaults to empty array when sessions key missing', async () => {
      mockSessionApiList.mockResolvedValue({});

      await chat.loadSessions();

      expect(chat.sessions.value).toEqual([]);
    });

    it('sets error on failure', async () => {
      mockSessionApiList.mockRejectedValue(new Error('Network error'));

      await chat.loadSessions();

      expect(chat.error.value).toBe('Network error');
    });
  });

  // -------------------------------------------------------------------------
  // createSession
  // -------------------------------------------------------------------------
  describe('createSession', () => {
    it('creates session, resets state, and connects stream', async () => {
      mockSessionApiCreate.mockResolvedValue({ session_id: 'sess-new' });
      mockSessionApiList.mockResolvedValue({ sessions: [] });

      await chat.createSession();

      expect(chat.sessionId.value).toBe('sess-new');
      expect(chat.messages.value).toEqual([]);
      expect(chat.streamingContent.value).toBe('');
      expect(mockSseConnect).toHaveBeenCalled();
    });

    it('sets error on failure', async () => {
      mockSessionApiCreate.mockRejectedValue(new Error('Create failed'));

      await chat.createSession();

      expect(chat.error.value).toBe('Create failed');
      expect(chat.sessionId.value).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // selectSession
  // -------------------------------------------------------------------------
  describe('selectSession', () => {
    it('loads session and parses conversation_log', async () => {
      const msgs = [{ role: 'user', content: 'Hello', timestamp: '2026-01-01T00:00:00Z' }];
      mockSessionApiGet.mockResolvedValue({
        id: 'sess-1',
        conversation_log: JSON.stringify(msgs),
        status: 'completed',
      });

      await chat.selectSession('sess-1');

      expect(chat.sessionId.value).toBe('sess-1');
      expect(chat.messages.value).toEqual(msgs);
      // Should NOT connect stream for non-active session
      expect(mockSseConnect).not.toHaveBeenCalled();
    });

    it('connects stream for active sessions', async () => {
      mockSessionApiGet.mockResolvedValue({
        id: 'sess-2',
        conversation_log: '[]',
        status: 'active',
      });

      await chat.selectSession('sess-2');

      expect(mockSseConnect).toHaveBeenCalled();
    });

    it('handles missing conversation_log', async () => {
      mockSessionApiGet.mockResolvedValue({
        id: 'sess-3',
        status: 'completed',
      });

      await chat.selectSession('sess-3');

      expect(chat.messages.value).toEqual([]);
    });

    it('handles corrupt conversation_log JSON', async () => {
      mockSessionApiGet.mockResolvedValue({
        id: 'sess-4',
        conversation_log: 'not-json',
        status: 'completed',
      });

      await chat.selectSession('sess-4');

      expect(chat.messages.value).toEqual([]);
      expect(chat.error.value).toContain('corrupt data');
    });

    it('sets error on API failure', async () => {
      mockSessionApiGet.mockRejectedValue(new Error('Session not found'));

      await chat.selectSession('sess-x');

      expect(chat.error.value).toBe('Session not found');
    });
  });

  // -------------------------------------------------------------------------
  // sendMessage
  // -------------------------------------------------------------------------
  describe('sendMessage', () => {
    beforeEach(async () => {
      // Pre-create a session so sendMessage doesn't auto-create
      mockSessionApiCreate.mockResolvedValue({ session_id: 'sess-1' });
      mockSessionApiList.mockResolvedValue({ sessions: [] });
      await chat.createSession();
      vi.clearAllMocks();
    });

    it('ignores blank messages', async () => {
      await chat.sendMessage('   ');

      expect(mockSessionApiSendChatMessage).not.toHaveBeenCalled();
      expect(chat.messages.value).toEqual([]);
    });

    it('adds user message optimistically and calls API', async () => {
      mockSessionApiSendChatMessage.mockResolvedValue({});

      await chat.sendMessage('Hello world');

      expect(chat.messages.value).toHaveLength(1);
      expect(chat.messages.value[0].role).toBe('user');
      expect(chat.messages.value[0].content).toBe('Hello world');
      expect(chat.isProcessing.value).toBe(true);
      expect(mockSessionApiSendChatMessage).toHaveBeenCalledWith(
        'sa-abc123',
        'sess-1',
        'Hello world',
        undefined,
      );
    });

    it('sets backend on user message when provided in options', async () => {
      mockSessionApiSendChatMessage.mockResolvedValue({});

      await chat.sendMessage('Hi', { backend: 'openai' });

      expect(chat.messages.value[0].backend).toBe('openai');
    });

    it('removes optimistic message and resets processing on API error', async () => {
      mockSessionApiSendChatMessage.mockRejectedValue(new Error('Send failed'));

      await chat.sendMessage('Hello');

      expect(chat.messages.value).toEqual([]);
      expect(chat.isProcessing.value).toBe(false);
      expect(chat.error.value).toBe('Send failed');
    });

    it('auto-creates session if none active', async () => {
      // Start fresh with no session
      const freshChat = useAiChat(ref('sa-xyz'));
      mockSessionApiCreate.mockResolvedValue({ session_id: 'sess-auto' });
      mockSessionApiList.mockResolvedValue({ sessions: [] });
      mockSessionApiSendChatMessage.mockResolvedValue({});

      await freshChat.sendMessage('auto-create test');

      expect(mockSessionApiCreate).toHaveBeenCalledWith('sa-xyz');
      expect(freshChat.sessionId.value).toBe('sess-auto');
      expect(freshChat.messages.value[0].content).toBe('auto-create test');
    });

    it('aborts if auto-create session fails', async () => {
      const freshChat = useAiChat(ref('sa-fail'));
      mockSessionApiCreate.mockRejectedValue(new Error('Cannot create'));

      await freshChat.sendMessage('wont work');

      expect(mockSessionApiSendChatMessage).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // endSession
  // -------------------------------------------------------------------------
  describe('endSession', () => {
    it('does nothing when no session is active', async () => {
      await chat.endSession();

      expect(mockSessionApiEnd).not.toHaveBeenCalled();
    });

    it('ends session, closes stream, and clears sessionId', async () => {
      // Set up an active session
      mockSessionApiCreate.mockResolvedValue({ session_id: 'sess-end' });
      mockSessionApiList.mockResolvedValue({ sessions: [] });
      await chat.createSession();
      vi.clearAllMocks();

      mockSessionApiEnd.mockResolvedValue({});
      mockSessionApiList.mockResolvedValue({ sessions: [] });

      await chat.endSession();

      expect(mockSessionApiEnd).toHaveBeenCalledWith('sa-abc123', 'sess-end');
      expect(mockSseClose).toHaveBeenCalled();
      expect(chat.sessionId.value).toBeNull();
    });

    it('sets error on failure', async () => {
      mockSessionApiCreate.mockResolvedValue({ session_id: 'sess-e' });
      mockSessionApiList.mockResolvedValue({ sessions: [] });
      await chat.createSession();

      mockSessionApiEnd.mockRejectedValue(new Error('End failed'));

      await chat.endSession();

      expect(chat.error.value).toBe('End failed');
    });
  });

  // -------------------------------------------------------------------------
  // SSE state_delta event handling
  // -------------------------------------------------------------------------
  describe('SSE state_delta handling', () => {
    it('handles message event — adds assistant message', () => {
      fireStateDelta({
        type: 'message',
        role: 'assistant',
        content: 'Hello from AI',
        timestamp: '2026-01-01T00:00:00Z',
      }, '1');

      expect(chat.messages.value).toHaveLength(1);
      expect(chat.messages.value[0]).toMatchObject({
        role: 'assistant',
        content: 'Hello from AI',
      });
    });

    it('deduplicates messages with same role and content', () => {
      fireStateDelta({ type: 'message', role: 'user', content: 'Dup' }, '1');
      fireStateDelta({ type: 'message', role: 'user', content: 'Dup' }, '2');

      expect(chat.messages.value).toHaveLength(1);
    });

    it('ignores message events without role or content', () => {
      fireStateDelta({ type: 'message', role: 'assistant' }, '1');
      fireStateDelta({ type: 'message', content: 'orphan' }, '2');

      expect(chat.messages.value).toHaveLength(0);
    });

    it('includes backend on message when present', () => {
      fireStateDelta({
        type: 'message',
        role: 'assistant',
        content: 'backend msg',
        backend: 'claude',
      }, '1');

      expect(chat.messages.value[0].backend).toBe('claude');
    });

    it('handles content_delta — accumulates streaming content', () => {
      fireStateDelta({ type: 'content_delta', content: 'chunk1' }, '1');
      fireStateDelta({ type: 'content_delta', content: ' chunk2' }, '2');

      expect(chat.streamingContent.value).toBe('chunk1 chunk2');
    });

    it('content_delta invokes streaming chunk callback', () => {
      const cb = vi.fn();
      chat.setOnStreamingChunk(cb);

      fireStateDelta({ type: 'content_delta', content: 'piece' }, '1');

      expect(cb).toHaveBeenCalledWith('piece');
    });

    it('handles finish — pushes final message and resets', () => {
      // Accumulate some streaming content first
      fireStateDelta({ type: 'content_delta', content: 'partial' }, '1');
      chat.isProcessing.value = true;

      fireStateDelta({ type: 'finish', backend: 'openai' }, '2');

      expect(chat.messages.value).toHaveLength(1);
      expect(chat.messages.value[0]).toMatchObject({
        role: 'assistant',
        content: 'partial',
        backend: 'openai',
      });
      expect(chat.streamingContent.value).toBe('');
      expect(chat.isProcessing.value).toBe(false);
    });

    it('finish with explicit content uses that over streamingContent', () => {
      fireStateDelta({ type: 'content_delta', content: 'old' }, '1');
      fireStateDelta({ type: 'finish', content: 'final answer' }, '2');

      expect(chat.messages.value[0].content).toBe('final answer');
    });

    it('finish with no content and no streaming does not add message', () => {
      fireStateDelta({ type: 'finish' }, '1');

      expect(chat.messages.value).toHaveLength(0);
    });

    it('handles status_change — toggles isProcessing', () => {
      fireStateDelta({ type: 'status_change', status: 'streaming' }, '1');
      expect(chat.isProcessing.value).toBe(true);

      fireStateDelta({ type: 'status_change', status: 'processing' }, '2');
      expect(chat.isProcessing.value).toBe(true);

      fireStateDelta({ type: 'status_change', status: 'idle' }, '3');
      expect(chat.isProcessing.value).toBe(false);
    });

    it('handles status_change error — stops processing', () => {
      chat.isProcessing.value = true;

      fireStateDelta({ type: 'status_change', status: 'error' }, '1');

      expect(chat.isProcessing.value).toBe(false);
    });

    it('handles error event — sets error and stops processing', () => {
      chat.isProcessing.value = true;

      fireStateDelta({ type: 'error', message: 'Something broke' }, '1');

      expect(chat.error.value).toBe('Something broke');
      expect(chat.isProcessing.value).toBe(false);
    });

    it('handles error event with no message', () => {
      fireStateDelta({ type: 'error' }, '1');

      expect(chat.error.value).toBe('Stream error');
    });

    it('handles full_sync — replaces messages', () => {
      // Pre-populate
      fireStateDelta({ type: 'message', role: 'user', content: 'old' }, '1');
      expect(chat.messages.value).toHaveLength(1);

      const synced = [
        { role: 'user', content: 'synced', timestamp: '2026-01-01T00:00:00Z' },
      ];
      fireStateDelta({ type: 'full_sync', messages: synced }, '2');

      expect(chat.messages.value).toEqual(synced);
      expect(chat.streamingContent.value).toBe('');
    });

    it('ignores unknown event types gracefully', () => {
      // Should not throw
      fireStateDelta({ type: 'unknown_type', data: 'whatever' }, '1');
      expect(chat.messages.value).toEqual([]);
    });
  });

  // -------------------------------------------------------------------------
  // Seq-based deduplication
  // -------------------------------------------------------------------------
  describe('seq deduplication', () => {
    it('drops events with seq <= lastSeq (replay dedup)', () => {
      fireStateDelta({ type: 'message', role: 'assistant', content: 'first' }, '5');
      fireStateDelta({ type: 'message', role: 'assistant', content: 'replay' }, '3');
      fireStateDelta({ type: 'message', role: 'assistant', content: 'also replay' }, '5');

      expect(chat.messages.value).toHaveLength(1);
      expect(chat.messages.value[0].content).toBe('first');
    });

    it('allows seq 0 events (unsequenced) through', () => {
      fireStateDelta({ type: 'message', role: 'assistant', content: 'a' }, '5');
      fireStateDelta({ type: 'message', role: 'assistant', content: 'b' }, '0');

      expect(chat.messages.value).toHaveLength(2);
    });
  });

  // -------------------------------------------------------------------------
  // Legacy message event handler
  // -------------------------------------------------------------------------
  describe('legacy message event handler', () => {
    it('handles legacy output messages', () => {
      capturedEvents.message?.(sseEvent({ type: 'output', content: 'legacy output' }));

      expect(chat.messages.value).toHaveLength(1);
      expect(chat.messages.value[0]).toMatchObject({
        role: 'assistant',
        content: 'legacy output',
      });
    });

    it('deduplicates legacy output messages', () => {
      capturedEvents.message?.(sseEvent({ type: 'output', content: 'same' }));
      capturedEvents.message?.(sseEvent({ type: 'output', content: 'same' }));

      expect(chat.messages.value).toHaveLength(1);
    });

    it('ignores heartbeat messages', () => {
      capturedEvents.message?.(sseEvent({ type: 'heartbeat' }));

      expect(chat.messages.value).toHaveLength(0);
    });

    it('handles non-JSON message gracefully', () => {
      // Should not throw
      capturedEvents.message?.({ data: 'not-json', lastEventId: '0' } as unknown as MessageEvent);
      expect(chat.messages.value).toHaveLength(0);
    });
  });

  // -------------------------------------------------------------------------
  // setOnStreamingChunk
  // -------------------------------------------------------------------------
  describe('setOnStreamingChunk', () => {
    it('registers callback invoked on content_delta', () => {
      const cb = vi.fn();
      chat.setOnStreamingChunk(cb);

      fireStateDelta({ type: 'content_delta', content: 'hello' }, '1');

      expect(cb).toHaveBeenCalledWith('hello');
    });
  });

  // -------------------------------------------------------------------------
  // Clearing / cleanup
  // -------------------------------------------------------------------------
  describe('cleanup', () => {
    it('createSession resets messages and streaming content', async () => {
      // Pre-populate some state
      fireStateDelta({ type: 'message', role: 'user', content: 'old' }, '1');
      chat.streamingContent.value = 'partial';

      mockSessionApiCreate.mockResolvedValue({ session_id: 'sess-new' });
      mockSessionApiList.mockResolvedValue({ sessions: [] });

      await chat.createSession();

      expect(chat.messages.value).toEqual([]);
      expect(chat.streamingContent.value).toBe('');
    });
  });
});
