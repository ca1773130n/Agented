import { ref, onUnmounted, type Ref } from 'vue';
import type { ConversationMessage, SuperAgent, SuperAgentSession } from '../services/api';
import { superAgentSessionApi, superAgentApi } from '../services/api';
import { useProcessGroups, type ToolCallDelta } from './useProcessGroups';
import { useAllMode } from './useAllMode';

/**
 * Single source of truth composable for ALL AI chat panel UIs.
 *
 * Manages session lifecycle, message state, SSE streaming via the
 * state_delta protocol (37-02), process groups, and cleanup.
 * Used by SuperAgentPlayground, AIBackendsPage, and any future chat UI.
 *
 * The state_delta protocol delivers named SSE events with seq-based
 * ordering and Last-Event-ID reconnection support.
 */
export function useAiChat(superAgentId: Ref<string>) {
  const sessionId = ref<string | null>(null);
  const messages = ref<ConversationMessage[]>([]);
  const isProcessing = ref(false);
  const streamingContent = ref('');
  const superAgent = ref<SuperAgent | null>(null);
  const sessions = ref<SuperAgentSession[]>([]);
  const error = ref<string | null>(null);

  // Process groups for tool call / reasoning rendering
  const processGroups = useProcessGroups();

  // All/Compound mode state management
  const allMode = useAllMode();

  // Seq tracking for de-duplication and reconnection
  let lastSeq = 0;

  // Track which backend is used for the current streaming response
  let _currentBackend: string | undefined;

  // Callback for streaming chunks (set by AiChatPanel when smd.js is initialized)
  let onStreamingChunkCallback: ((text: string) => void) | null = null;

  let eventSource: EventSource | null = null;

  function setOnStreamingChunk(cb: (text: string) => void) {
    onStreamingChunkCallback = cb;
  }

  async function loadSuperAgent() {
    try {
      superAgent.value = await superAgentApi.get(superAgentId.value);
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load super agent';
    }
  }

  async function loadSessions() {
    try {
      const result = await superAgentSessionApi.list(superAgentId.value);
      sessions.value = result.sessions || [];
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load sessions';
    }
  }

  async function createSession() {
    try {
      error.value = null;
      const result = await superAgentSessionApi.create(superAgentId.value);
      sessionId.value = result.session_id;
      messages.value = [];
      streamingContent.value = '';
      lastSeq = 0;
      processGroups.clearGroups();
      connectStream();
      await loadSessions();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to create session';
    }
  }

  async function selectSession(sessId: string) {
    try {
      error.value = null;
      closeStream();
      const sess = await superAgentSessionApi.get(superAgentId.value, sessId);
      sessionId.value = sess.id;

      // Parse conversation_log from JSON if available
      if (sess.conversation_log) {
        try {
          const parsed = JSON.parse(sess.conversation_log);
          messages.value = Array.isArray(parsed) ? parsed : [];
        } catch {
          messages.value = [];
        }
      } else {
        messages.value = [];
      }

      streamingContent.value = '';
      lastSeq = 0;
      processGroups.clearGroups();
      if (sess.status === 'active') {
        connectStream();
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load session';
    }
  }

  async function sendMessage(
    content: string,
    options?: { backend?: string; account_id?: string; model?: string },
  ) {
    if (!content.trim()) return;

    // Auto-create session if none active
    if (!sessionId.value) {
      await createSession();
      if (!sessionId.value) return; // Creation failed
    }

    _currentBackend = options?.backend;

    messages.value.push({
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
      backend: _currentBackend,
    });

    isProcessing.value = true;
    streamingContent.value = '';
    processGroups.clearGroups();
    error.value = null;

    // All/Compound mode dispatch
    if (allMode.chatMode.value !== 'single') {
      const modeOptions = {
        ...options,
        mode: allMode.chatMode.value as string,
      };
      // Pre-activate allMode BEFORE the POST so SSE events arriving while
      // the request is in-flight are properly intercepted (race condition fix).
      // Also clear any stale data from a previous all-mode run.
      allMode.startAllMode([]);
      try {
        const response = await superAgentSessionApi.sendChatMessage(
          superAgentId.value,
          sessionId.value,
          content,
          modeOptions,
        );
        // Finalize the backend list from the POST response so we know exactly
        // which backends to expect. This prevents premature deactivation when
        // fast backends complete before the POST response arrives (race fix).
        if (response.backends) {
          allMode.finalizeBackendList(
            Object.keys(response.backends as Record<string, unknown>),
          );
        }
      } catch (e) {
        error.value = e instanceof Error ? e.message : 'Failed to send message';
        messages.value.pop();
        isProcessing.value = false;
        allMode.reset();
      }
      return; // Skip single-mode path
    }

    try {
      await superAgentSessionApi.sendChatMessage(
        superAgentId.value,
        sessionId.value,
        content,
        options,
      );
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to send message';
      // Remove the optimistic user message on failure
      messages.value.pop();
      isProcessing.value = false;
    }
    // Note: isProcessing is managed by SSE status_change events, not the POST response
  }

  async function endSession() {
    if (!sessionId.value) return;

    try {
      await superAgentSessionApi.end(superAgentId.value, sessionId.value);
      closeStream();
      sessionId.value = null;
      processGroups.clearGroups();
      await loadSessions();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to end session';
    }
  }

  function connectStream() {
    if (!sessionId.value) return;

    closeStream();
    eventSource = superAgentSessionApi.chatStream(
      superAgentId.value,
      sessionId.value,
    );

    // Listen for the named "state_delta" event from the SSE protocol
    eventSource.addEventListener('state_delta', (event: Event) => {
      const msgEvent = event as MessageEvent;
      try {
        const data = JSON.parse(msgEvent.data);

        // Track seq for de-duplication
        const seq = parseInt(msgEvent.lastEventId || '0', 10);
        if (seq > 0 && seq <= lastSeq) {
          return; // Duplicate from reconnection replay
        }
        if (seq > 0) {
          lastSeq = seq;
        }

        handleStateDelta(data);
      } catch {
        // Ignore unparseable events (e.g., heartbeats)
      }
    });

    // Also handle generic message events for backward compatibility
    eventSource.addEventListener('message', (event: Event) => {
      const msgEvent = event as MessageEvent;
      try {
        const data = JSON.parse(msgEvent.data);
        // Heartbeat check
        if (data.type === 'heartbeat') return;
        // Legacy output format
        if (data.type === 'output' && data.content) {
          const isDuplicate = messages.value.some(
            (m) => m.content === data.content && m.role === 'assistant',
          );
          if (!isDuplicate) {
            messages.value.push({
              role: 'assistant',
              content: data.content,
              timestamp: new Date().toISOString(),
            });
          }
        }
      } catch {
        // Ignore
      }
    });

    eventSource.addEventListener('error', () => {
      // EventSource auto-reconnects; no explicit error handling needed
    });
  }

  /**
   * Dispatch state_delta events by type.
   */
  function handleStateDelta(data: Record<string, unknown>) {
    // Multi-backend event interception for All/Compound modes
    if (allMode.isAllModeActive.value) {
      const wasActive = allMode.isAllModeActive.value;
      const handled = allMode.handleMultiBackendDelta(data);
      if (handled) {
        // Clear processing state when all-mode finishes
        // (backend_complete for all backends or synthesis_complete)
        if (wasActive && !allMode.isAllModeActive.value) {
          isProcessing.value = false;
        }
        return; // Event consumed by multi-backend handler
      }
    }

    const type = data.type as string;

    switch (type) {
      case 'message': {
        // Push complete message with de-duplication by seq
        const msg = data as {
          role?: string;
          content?: string;
          timestamp?: string;
          seq?: number;
          backend?: string;
        };
        if (msg.role && msg.content) {
          // De-duplicate by content + role only (not timestamp).
          // The optimistic user message added in sendMessage() has a
          // client-generated timestamp, while the server echo arrives
          // without one, so timestamp comparison always fails.
          const isDuplicate = messages.value.some(
            (m) => m.content === msg.content && m.role === msg.role,
          );
          if (!isDuplicate) {
            const entry: ConversationMessage = {
              role: msg.role as 'user' | 'assistant' | 'system',
              content: msg.content,
              timestamp: msg.timestamp || new Date().toISOString(),
            };
            if (msg.backend) {
              entry.backend = msg.backend;
            }
            messages.value.push(entry);
          }
        }
        break;
      }

      case 'content_delta': {
        // Accumulate streaming content
        const delta = data as { content?: string };
        if (delta.content) {
          streamingContent.value += delta.content;
          if (onStreamingChunkCallback) {
            onStreamingChunkCallback(delta.content);
          }
        }
        break;
      }

      case 'tool_call': {
        // Process tool call deltas through process groups
        const toolCall = data as unknown as ToolCallDelta;
        processGroups.processToolCallDelta(toolCall);
        break;
      }

      case 'finish': {
        // Finalize streaming: push complete assistant message.
        // Use the server-resolved backend (from the finish event) so each
        // message permanently records which backend produced it, regardless
        // of later dropdown changes.
        const finish = data as { content?: string; backend?: string };
        const finalContent = finish.content || streamingContent.value;
        const resolvedBackend = finish.backend || _currentBackend;
        if (finalContent) {
          messages.value.push({
            role: 'assistant',
            content: finalContent,
            timestamp: new Date().toISOString(),
            backend: resolvedBackend,
          });
        }
        streamingContent.value = '';
        isProcessing.value = false;
        _currentBackend = undefined;
        break;
      }

      case 'status_change': {
        // Update processing state based on status
        const status = data as { status?: string };
        if (status.status === 'streaming' || status.status === 'processing') {
          isProcessing.value = true;
        } else if (status.status === 'idle' || status.status === 'error') {
          isProcessing.value = false;
        }
        break;
      }

      case 'error': {
        // Display error
        const errData = data as { message?: string };
        error.value = errData.message || 'Stream error';
        isProcessing.value = false;
        break;
      }

      case 'full_sync': {
        // Replace all state with synced data
        const sync = data as { messages?: ConversationMessage[] };
        if (sync.messages) {
          messages.value = sync.messages;
        }
        streamingContent.value = '';
        processGroups.clearGroups();
        break;
      }

      default:
        // Unknown event type -- ignore
        break;
    }
  }

  function closeStream() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  function cleanup() {
    closeStream();
    allMode.reset();
  }

  onUnmounted(cleanup);

  return {
    sessionId,
    sessions,
    messages,
    isProcessing,
    streamingContent,
    superAgent,
    error,
    processGroups: processGroups.groups,
    loadSuperAgent,
    loadSessions,
    createSession,
    selectSession,
    sendMessage,
    endSession,
    setOnStreamingChunk,
    // All/Compound mode state
    chatMode: allMode.chatMode,
    backendResponses: allMode.backendResponses,
    synthesisState: allMode.synthesisState,
    isAllModeActive: allMode.isAllModeActive,
    allModeReset: allMode.reset,
  };
}
