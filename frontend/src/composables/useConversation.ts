import { ref, shallowRef, nextTick, onUnmounted } from 'vue';
import type { ConversationMessage } from '../services/api';
import { ApiError } from '../services/api';
import { useStreamingParser } from './useStreamingParser';
import { useToast } from './useToast';

/**
 * Shared conversation API interface. Each entity's conversation API
 * (hookConversationApi, commandConversationApi, etc.) conforms to this shape.
 */
export interface ConversationApi {
  list?: () => Promise<{ conversations: { id: string; entity_type: string; status: string; updated_at: string }[] }>;
  start: () => Promise<{ conversation_id: string; message: string }>;
  get?: (convId: string) => Promise<{ id: string; status: string; messages_parsed?: any[] }>;
  sendMessage: (convId: string, message: string, options?: { backend?: string; account_id?: string; model?: string }) => Promise<{ message_id: string; status: string }>;
  stream: (convId: string) => EventSource;
  finalize: (convId: string) => Promise<any>;
  resume?: (convId: string) => Promise<{ message: string; conversation_id: string }>;
  abandon: (convId: string) => Promise<{ message: string }>;
}

/**
 * A config parser function takes the assistant's response content and tries to
 * extract entity-specific configuration from it. Returns null if no config found.
 */
export type ConfigParser<T> = (content: string) => T | null;

/**
 * Creates a config parser that extracts JSON between `---MARKER---` and `---END_CONFIG---`.
 * All entity config parsers follow this exact pattern.
 */
export function createConfigParser<T>(marker: string): ConfigParser<T> {
  return (content: string): T | null => {
    if (!content.includes(marker)) return null;
    try {
      const start = content.indexOf(marker) + marker.length;
      const end = content.indexOf('---END_CONFIG---');
      if (end === -1) return null;
      return JSON.parse(content.substring(start, end).trim());
    } catch {
      return null;
    }
  };
}

/**
 * Optional parameters for backend/account/model selection.
 * All fields default to "auto" behavior when omitted.
 * Stored as reactive refs for runtime updates via setters.
 */
export interface ConversationOptions {
  /** Backend type for conversations: 'auto' (default) | 'claude' | 'opencode' | etc. */
  backend?: string;
  /** Specific account ID, or null for auto-selection */
  accountId?: string | null;
  /** Specific model name, or null for backend default */
  model?: string | null;
}

export function useConversation<TConfig>(
  api: ConversationApi,
  parseConfig: ConfigParser<TConfig>,
  options?: ConversationOptions,
) {
  const showToast = useToast();

  const conversationId = ref<string | null>(null);
  const messages = ref<ConversationMessage[]>([]);
  const inputMessage = ref('');
  const isProcessing = ref(false);
  const streamingContent = shallowRef('');
  const chatContainer = ref<HTMLElement | null>(null);
  const eventSourceRef = ref<EventSource | null>(null);
  const canFinalize = ref(false);
  const chatStarted = ref(false);
  const detectedConfig = ref<TConfig | null>(null) as ReturnType<typeof ref<TConfig | null>>;
  const isFinalizing = ref(false);

  // Backend/account/model selection state (for future use when backend API supports them)
  const selectedBackend = ref(options?.backend ?? 'auto');
  const selectedAccountId = ref<string | null>(options?.accountId ?? null);
  const selectedModel = ref<string | null>(options?.model ?? null);

  function setBackend(backend: string) { selectedBackend.value = backend; }
  function setAccountId(accountId: string | null) { selectedAccountId.value = accountId; }
  function setModel(model: string | null) { selectedModel.value = model; }

  // smd.js streaming parser (shared composable)
  const streamingParser = useStreamingParser({ onFlush: scrollToBottom });

  function scrollToBottom() {
    nextTick(() => {
      if (chatContainer.value) {
        chatContainer.value.scrollTop = chatContainer.value.scrollHeight;
      }
    });
  }

  function connectToStream() {
    if (!conversationId.value) return;

    eventSourceRef.value = api.stream(conversationId.value);

    eventSourceRef.value.addEventListener('message', (event) => {
      const data = JSON.parse(event.data);
      if (data.role !== 'system') {
        // De-duplicate: skip if a message with the same timestamp and content already exists
        const isDuplicate = messages.value.some(
          (m) => m.timestamp === data.timestamp && m.content === data.content,
        );
        if (!isDuplicate) {
          messages.value.push(data);
          scrollToBottom();
        }
      }
    });

    eventSourceRef.value.addEventListener('response_start', () => {
      isProcessing.value = true;
      streamingContent.value = '';
    });

    eventSourceRef.value.addEventListener('response_chunk', (event) => {
      const data = JSON.parse(event.data);
      // Accumulate raw text for response_complete fallback
      streamingContent.value += data.content;
      // Feed to smd.js via rAF batch
      streamingParser.write(data.content);
    });

    eventSourceRef.value.addEventListener('response_complete', (event) => {
      const data = JSON.parse(event.data);
      isProcessing.value = false;
      streamingParser.finalize();

      if (data.content) {
        const resolvedBackend = data.backend || (selectedBackend.value !== 'auto' ? selectedBackend.value : undefined);
        const entry: ConversationMessage = {
          role: 'assistant',
          content: data.content,
          timestamp: new Date().toISOString(),
        };
        if (resolvedBackend) {
          entry.backend = resolvedBackend;
        }
        messages.value.push(entry);

        // Update config only when a new one is detected in this response.
        // If the response has no config marker, keep the previous config
        // (the AI may be asking follow-up questions about the same config).
        const config = parseConfig(data.content);
        if (config) {
          detectedConfig.value = config;
          canFinalize.value = true;
        }
      }

      streamingContent.value = '';
      scrollToBottom();
    });

    eventSourceRef.value.addEventListener('error', (event) => {
      try {
        const msgEvent = event as MessageEvent;
        if (msgEvent.data) {
          const data = JSON.parse(msgEvent.data);
          showToast(data.error || 'Stream error', 'error');
        }
      } catch {
        // Server-sent error event with unparseable data -- ignore
      }
      isProcessing.value = false;
    });

    eventSourceRef.value.onerror = () => {
      // Native EventSource connection error (network drop, server close).
      // EventSource auto-reconnects by default; no toast needed.
    };
  }

  async function startConversation() {
    if (chatStarted.value) return;
    chatStarted.value = true;

    try {
      const result = await api.start();
      conversationId.value = result.conversation_id;
      connectToStream();
    } catch (e) {
      chatStarted.value = false;
      if (e instanceof ApiError) {
        showToast(e.message, 'error');
      } else {
        showToast('Failed to start conversation', 'error');
      }
    }
  }

  async function sendMessage() {
    if (!conversationId.value || !inputMessage.value.trim() || isProcessing.value) return;

    const message = inputMessage.value.trim();
    inputMessage.value = '';

    messages.value.push({
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    });
    scrollToBottom();

    isProcessing.value = true;

    try {
      await api.sendMessage(conversationId.value, message, {
        backend: selectedBackend.value !== 'auto' ? selectedBackend.value : undefined,
        account_id: selectedAccountId.value || undefined,
        model: selectedModel.value || undefined,
      });
    } catch (e) {
      messages.value.pop();
      isProcessing.value = false;
      if (e instanceof ApiError) {
        showToast(e.message, 'error');
      } else {
        showToast('Failed to send message', 'error');
      }
    }
  }

  async function finalize(): Promise<any> {
    if (!conversationId.value || isFinalizing.value) return null;

    isFinalizing.value = true;
    try {
      const result = await api.finalize(conversationId.value);
      return result;
    } catch (e) {
      if (e instanceof ApiError) {
        showToast(e.message, 'error');
      } else {
        showToast('Failed to finalize', 'error');
      }
      return null;
    } finally {
      isFinalizing.value = false;
    }
  }

  async function resumeConversation(convId: string) {
    if (chatStarted.value) return;
    chatStarted.value = true;

    try {
      if (api.resume) {
        await api.resume(convId);
      }
      conversationId.value = convId;

      // Load existing messages
      if (api.get) {
        const conv = await api.get(convId);
        if (conv.messages_parsed) {
          messages.value = conv.messages_parsed;
          // Check if any assistant message has a config marker
          for (const msg of messages.value) {
            if (msg.role === 'assistant') {
              const config = parseConfig(msg.content);
              if (config) {
                detectedConfig.value = config;
                canFinalize.value = true;
              }
            }
          }
        }
      }

      connectToStream();
    } catch {
      chatStarted.value = false;
      showToast('Failed to resume conversation', 'error');
    }
  }

  const activeConversations = ref<{ id: string; updated_at: string }[]>([]);

  async function checkActiveConversations() {
    if (!api.list) return;
    try {
      const result = await api.list();
      activeConversations.value = result.conversations || [];
    } catch {
      // Silently fail
    }
  }

  async function abandonConversation() {
    if (conversationId.value) {
      try {
        await api.abandon(conversationId.value);
      } catch {
        // Ignore errors on abandon
      }
    }
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function cleanup() {
    streamingParser.finalize();
    if (eventSourceRef.value) {
      eventSourceRef.value.close();
    }
  }

  onUnmounted(cleanup);

  return {
    conversationId,
    messages,
    inputMessage,
    isProcessing,
    streamingContent,
    chatContainer,
    canFinalize,
    isFinalizing,
    chatStarted,
    detectedConfig,
    activeConversations,
    selectedBackend,
    selectedAccountId,
    selectedModel,
    startConversation,
    resumeConversation,
    checkActiveConversations,
    sendMessage,
    finalize,
    abandonConversation,
    handleKeyDown,
    initStreamingParser: streamingParser.init,
    scrollToBottom,
    cleanup,
    setBackend,
    setAccountId,
    setModel,
  };
}
