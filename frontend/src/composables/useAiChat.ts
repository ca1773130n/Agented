import { ref, onUnmounted, type Ref } from 'vue';
import type { ConversationMessage, SuperAgent, SuperAgentSession } from '../services/api';
import { superAgentSessionApi, superAgentApi } from '../services/api';
import { useProcessGroups } from './useProcessGroups';
import { useAllMode } from './useAllMode';
import { useEventSource } from './useEventSource';

/**
 * Discriminated union of all state_delta SSE event payloads.
 * Enables type-safe narrowing in handleStateDelta without double-casting.
 */
type StateDelta =
  | { type: 'message'; role?: string; content?: string; timestamp?: string; seq?: number; backend?: string }
  | { type: 'content_delta'; content?: string }
  | { type: 'tool_call'; id: string; name?: string; arguments?: string }
  | { type: 'finish'; content?: string; backend?: string }
  | { type: 'status_change'; status?: string }
  | { type: 'error'; message?: string }
  | { type: 'full_sync'; messages?: ConversationMessage[] };

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

  // Reconnect watchdog -- SSE comment keepalives are invisible to EventSource,
  // so the client tracks named-event activity instead. If no named event arrives
  // within HEARTBEAT_TIMEOUT_MS (server sends keepalives every 30 s, so 65 s gives
  // ample margin), the connection is assumed stale and the stream is restarted.
  // On reconnect, EventSource automatically sends Last-Event-ID; the server replays
  // missed events from that seq so no messages are lost.
  const HEARTBEAT_TIMEOUT_MS = 65_000;
  let _heartbeatTimer: ReturnType<typeof setTimeout> | null = null;

  function _resetHeartbeat() {
    if (_heartbeatTimer) clearTimeout(_heartbeatTimer);
    _heartbeatTimer = setTimeout(() => {
      if (sessionId.value && sseGetSource()) {
        console.warn('[useAiChat] No SSE activity for 65 s -- reconnecting');
        connectStream();
      }
    }, HEARTBEAT_TIMEOUT_MS);
  }

  function _clearHeartbeat() {
    if (_heartbeatTimer) {
      clearTimeout(_heartbeatTimer);
      _heartbeatTimer = null;
    }
  }

  function setOnStreamingChunk(cb: (text: string) => void) {
    onStreamingChunkCallback = cb;
  }

  // SSE lifecycle managed by useEventSource
  const { connect: sseConnect, close: sseClose, getSource: sseGetSource } = useEventSource({
    sourceFactory: () => superAgentSessionApi.chatStream(
      superAgentId.value,
      sessionId.value!,
    ),
    events: {
      // Named "state_delta" event from the SSE protocol
      state_delta: (event: MessageEvent) => {
        try {
          _resetHeartbeat(); // any named event resets the stale-connection timer
          const data = JSON.parse(event.data) as StateDelta;

          // Track seq for de-duplication
          const seq = parseInt(event.lastEventId || '0', 10);
          if (seq > 0 && seq <= lastSeq) {
            return; // Duplicate from reconnection replay
          }
          if (seq > 0) {
            lastSeq = seq;
          }

          handleStateDelta(data);
        } catch (e) {
          console.warn('[useAiChat] Failed to parse state_delta event:', e, event.data);
        }
      },
      // Generic message events for backward compatibility
      message: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
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
        } catch (e) {
          console.warn('[useAiChat] Failed to parse message event:', e, event.data);
        }
      },
      error: () => {
        // EventSource auto-reconnects; no explicit error handling needed
      },
    },
    onOpen: () => {
      _resetHeartbeat();
    },
  });

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
        } catch (e) {
          console.warn('Failed to parse conversation_log:', e);
          error.value = 'Chat history could not be loaded (corrupt data)';
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
    options?: { backend?: string; account_id?: string; model?: string; chat_mode?: string },
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
    sseConnect();

    // Start watchdog -- will reconnect if no named event arrives within timeout
    _resetHeartbeat();
  }

  function handleMessage(data: Extract<StateDelta, { type: 'message' }>) {
    // Push complete message with de-duplication by seq
    if (data.role && data.content) {
      // De-duplicate by content + role only (not timestamp).
      // The optimistic user message added in sendMessage() has a
      // client-generated timestamp, while the server echo arrives
      // without one, so timestamp comparison always fails.
      const isDuplicate = messages.value.some(
        (m) => m.content === data.content && m.role === data.role,
      );
      if (!isDuplicate) {
        const entry: ConversationMessage = {
          role: data.role as 'user' | 'assistant' | 'system',
          content: data.content,
          timestamp: data.timestamp || new Date().toISOString(),
        };
        if (data.backend) {
          entry.backend = data.backend;
        }
        messages.value.push(entry);
      }
    }
  }

  function handleContentDelta(data: Extract<StateDelta, { type: 'content_delta' }>) {
    // Accumulate streaming content
    if (data.content) {
      streamingContent.value += data.content;
      if (onStreamingChunkCallback) {
        onStreamingChunkCallback(data.content);
      }
    }
  }

  function handleToolUse(data: Extract<StateDelta, { type: 'tool_call' }>) {
    // data is narrowed to { type: 'tool_call'; id: string; name?: string; arguments?: string }
    // which is structurally compatible with ToolCallDelta (type: 'tool_call' in ProcessGroupType)
    processGroups.processToolCallDelta(data);
  }

  function handleFinish(data: Extract<StateDelta, { type: 'finish' }>) {
    // Finalize streaming: push complete assistant message.
    // Use the server-resolved backend (from the finish event) so each
    // message permanently records which backend produced it, regardless
    // of later dropdown changes.
    const finalContent = data.content || streamingContent.value;
    const resolvedBackend = data.backend || _currentBackend;
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
  }

  function handleStatusChange(data: Extract<StateDelta, { type: 'status_change' }>) {
    // Update processing state based on status
    if (data.status === 'streaming' || data.status === 'processing') {
      isProcessing.value = true;
    } else if (data.status === 'idle' || data.status === 'error') {
      isProcessing.value = false;
    }
  }

  function handleError(data: Extract<StateDelta, { type: 'error' }>) {
    // Display error
    error.value = data.message || 'Stream error';
    isProcessing.value = false;
  }

  function handleFullSync(data: Extract<StateDelta, { type: 'full_sync' }>) {
    // Replace all state with synced data
    if (data.messages) {
      messages.value = data.messages;
    }
    streamingContent.value = '';
    processGroups.clearGroups();
  }

  /**
   * Dispatch state_delta events by type.
   * Switches on data.type so TypeScript narrows each case automatically.
   */
  function handleStateDelta(data: StateDelta) {
    // Multi-backend event interception for All/Compound modes
    if (allMode.isAllModeActive.value) {
      const wasActive = allMode.isAllModeActive.value;
      const handled = allMode.handleMultiBackendDelta(data as unknown as Record<string, unknown>);
      if (handled) {
        // Clear processing state when all-mode finishes
        // (backend_complete for all backends or synthesis_complete)
        if (wasActive && !allMode.isAllModeActive.value) {
          isProcessing.value = false;
        }
        return; // Event consumed by multi-backend handler
      }
    }

    switch (data.type) {
      case 'message':        handleMessage(data); break;
      case 'content_delta':  handleContentDelta(data); break;
      case 'tool_call':      handleToolUse(data); break;
      case 'finish':         handleFinish(data); break;
      case 'status_change':  handleStatusChange(data); break;
      case 'error':          handleError(data); break;
      case 'full_sync':      handleFullSync(data); break;
      default:               break; // Unknown event type -- ignore
    }
  }

  function closeStream() {
    _clearHeartbeat();
    sseClose();
  }

  function cleanup() {
    closeStream();
    _clearHeartbeat();
    allMode.reset();
  }

  // SSE connection cleanup is handled by useEventSource's onUnmounted.
  // This separate onUnmounted handles heartbeat timers and allMode reset.
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
