import { describe, it, expect, vi, beforeEach } from 'vitest';
import { flushPromises } from '@vue/test-utils';

// ---------------------------------------------------------------------------
// Mocks -- declared before composable import so vi.mock hoisting works.
// ---------------------------------------------------------------------------

const mockShowToast = vi.fn();
vi.mock('../useToast', () => ({
  useToast: () => mockShowToast,
}));

// Mock useStreamingParser
const mockStreamingInit = vi.fn();
const mockStreamingWrite = vi.fn();
const mockStreamingFinalize = vi.fn();

vi.mock('../useStreamingParser', () => ({
  useStreamingParser: () => ({
    init: mockStreamingInit,
    write: mockStreamingWrite,
    finalize: mockStreamingFinalize,
    destroy: vi.fn(),
  }),
}));

// Mock useEventSource -- capture SSE event handlers
let capturedEvents: Record<string, (event: MessageEvent) => void> = {};
const mockSseConnect = vi.fn();
const mockSseClose = vi.fn();

vi.mock('../useEventSource', () => ({
  useEventSource: (opts: {
    events?: Record<string, (event: MessageEvent) => void>;
  }) => {
    capturedEvents = opts.events || {};
    return { connect: mockSseConnect, close: mockSseClose, getSource: vi.fn() };
  },
  safeParseSSE: <T>(event: MessageEvent): T | null => {
    try {
      return JSON.parse(event.data) as T;
    } catch {
      return null;
    }
  },
}));

// Mock Vue's onUnmounted
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

import { useConversation, createConfigParser, type ConversationApi } from '../useConversation';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sseEvent(data: unknown): MessageEvent {
  return { data: JSON.stringify(data) } as MessageEvent;
}

function createMockApi(overrides: Partial<ConversationApi> = {}): ConversationApi {
  return {
    start: vi.fn().mockResolvedValue({ conversation_id: 'conv-123', message: 'ok' }),
    sendMessage: vi.fn().mockResolvedValue({ message_id: 'msg-1', status: 'sent' }),
    stream: vi.fn().mockReturnValue({ addEventListener: vi.fn(), close: vi.fn() }),
    finalize: vi.fn().mockResolvedValue({ result: 'done' }),
    abandon: vi.fn().mockResolvedValue({ message: 'abandoned' }),
    ...overrides,
  };
}

const parseTestConfig = createConfigParser<{ name: string }>('---TEST_CONFIG---');

describe('useConversation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedEvents = {};
  });

  it('starts in idle state', () => {
    const api = createMockApi();
    const conv = useConversation(api, parseTestConfig);

    expect(conv.conversationId.value).toBeNull();
    expect(conv.chatStarted.value).toBe(false);
    expect(conv.isProcessing.value).toBe(false);
    expect(conv.messages.value).toEqual([]);
  });

  it('startConversation sets conversationId and connects SSE', async () => {
    const api = createMockApi();
    const conv = useConversation(api, parseTestConfig);

    await conv.startConversation();
    await flushPromises();

    expect(conv.conversationId.value).toBe('conv-123');
    expect(conv.chatStarted.value).toBe(true);
    expect(mockSseConnect).toHaveBeenCalled();
  });

  it('startConversation shows toast on error', async () => {
    const api = createMockApi({
      start: vi.fn().mockRejectedValue(new Error('Server down')),
    });
    const conv = useConversation(api, parseTestConfig);

    await conv.startConversation();
    await flushPromises();

    expect(conv.chatStarted.value).toBe(false);
    expect(mockShowToast).toHaveBeenCalledWith('Failed to start conversation', 'error');
  });

  it('sendMessage adds user message and calls API', async () => {
    const api = createMockApi();
    const conv = useConversation(api, parseTestConfig);

    await conv.startConversation();
    conv.inputMessage.value = 'Hello!';
    await conv.sendMessage();
    await flushPromises();

    expect(conv.messages.value).toHaveLength(1);
    expect(conv.messages.value[0].role).toBe('user');
    expect(conv.messages.value[0].content).toBe('Hello!');
    expect(api.sendMessage).toHaveBeenCalledWith('conv-123', 'Hello!', expect.any(Object));
  });

  it('sendMessage does nothing when input is empty', async () => {
    const api = createMockApi();
    const conv = useConversation(api, parseTestConfig);

    await conv.startConversation();
    conv.inputMessage.value = '   ';
    await conv.sendMessage();

    expect(api.sendMessage).not.toHaveBeenCalled();
  });

  it('SSE response_complete pushes assistant message', async () => {
    const api = createMockApi();
    const conv = useConversation(api, parseTestConfig);

    await conv.startConversation();

    // Simulate SSE response_complete event
    capturedEvents['response_complete'](sseEvent({ content: 'AI response' }));

    expect(conv.messages.value.some((m) => m.role === 'assistant' && m.content === 'AI response')).toBe(true);
    expect(conv.isProcessing.value).toBe(false);
  });

  it('SSE response_complete detects config in response', async () => {
    const api = createMockApi();
    const conv = useConversation(api, parseTestConfig);

    await conv.startConversation();

    const content = 'Here is the config:\n---TEST_CONFIG---\n{"name":"MyBot"}\n---END_CONFIG---';
    capturedEvents['response_complete'](sseEvent({ content }));

    expect(conv.detectedConfig.value).toEqual({ name: 'MyBot' });
    expect(conv.canFinalize.value).toBe(true);
  });

  it('finalize calls API and returns result', async () => {
    const api = createMockApi();
    const conv = useConversation(api, parseTestConfig);

    await conv.startConversation();
    const result = await conv.finalize();

    expect(api.finalize).toHaveBeenCalledWith('conv-123');
    expect(result).toEqual({ result: 'done' });
  });

  it('cleanup closes SSE and finalizes streaming parser', async () => {
    const api = createMockApi();
    const conv = useConversation(api, parseTestConfig);

    await conv.startConversation();
    conv.cleanup();

    expect(mockSseClose).toHaveBeenCalled();
    expect(mockStreamingFinalize).toHaveBeenCalled();
  });
});

describe('createConfigParser', () => {
  it('extracts JSON between marker and END_CONFIG', () => {
    const parser = createConfigParser<{ key: string }>('---MY_MARKER---');
    const content = 'text\n---MY_MARKER---\n{"key":"value"}\n---END_CONFIG---\nmore text';
    expect(parser(content)).toEqual({ key: 'value' });
  });

  it('returns null when marker is missing', () => {
    const parser = createConfigParser<{ key: string }>('---MY_MARKER---');
    expect(parser('no marker here')).toBeNull();
  });

  it('returns null when END_CONFIG is missing', () => {
    const parser = createConfigParser<{ key: string }>('---MY_MARKER---');
    expect(parser('---MY_MARKER---\n{"key":"value"}')).toBeNull();
  });

  it('returns null for invalid JSON between markers', () => {
    const parser = createConfigParser<{ key: string }>('---MY_MARKER---');
    expect(parser('---MY_MARKER---\nnot json\n---END_CONFIG---')).toBeNull();
  });
});
