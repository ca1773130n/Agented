<script setup lang="ts">
/**
 * Chat-style renderer on top of a GRD project session.
 *
 * Strategy: spawn ``claude`` with ``--print --input-format stream-json
 * --output-format stream-json --verbose``. This keeps the subprocess
 * alive while reading user messages from stdin (as JSON envelopes,
 * formatted server-side) and emitting one JSON event per line on
 * stdout. The backend's existing stream-json parser
 * (``_extract_stream_json_text``) lifts the text out, so the SSE
 * stream the frontend sees is already clean prose — no TUI banner,
 * no box-drawing chars, no ANSI escapes.
 *
 * The earlier attempt (v0.7.42) started bare ``claude``, which drops
 * into the interactive TUI and leaks its welcome panel / box-drawing
 * characters into the chat bubble. Hence v0.7.43.
 *
 * Why this exists vs. the SuperAgent playground:
 *   - GRD sessions still spawn arbitrary commands (claude, ralph_loop,
 *     team_spawn, etc.) — they're the right tool when you want a real
 *     subprocess that can talk to the filesystem and accept stdin.
 *   - The team-spawn / ralph-loop flows keep their PTY model. This
 *     view is a thin alternative for one specific case: talking to
 *     claude in the project's worktree as if it were a chatbot.
 */
import { ref, toRef, onMounted, computed } from 'vue';
import { AiChatPanelManaged } from '@ai-accounts/vue-styled';
import { useProjectSession } from '../../composables/useProjectSession';
import { useToast } from '../../composables/useToast';

interface ChatMsg {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
}

const props = defineProps<{ projectId: string }>();

const showToast = useToast();
const session = useProjectSession(toRef(props, 'projectId'));

const messages = ref<ChatMsg[]>([]);
const streamingContent = ref('');
const inputMessage = ref('');

// "Thinking" state for the chat panel. Tracked locally rather than
// reading ``session.isStreaming`` directly because the latter flips
// true the moment SSE connects — well before the user has even typed
// the first message, which made the panel look stuck at "AI is
// thinking..." straight after Start.
const awaitingResponse = ref(false);

// Diagnostic line shown under the input when no output has arrived
// within a few seconds after sending. Cleared on first chunk / on
// session complete. Helps tell apart "still generating" from "claude
// crashed and we don't know".
const diagnostic = ref<string | null>(null);
let diagnosticTimer: ReturnType<typeof setTimeout> | null = null;

const hasActiveSession = computed(() => Boolean(session.activeSessionId.value));

/**
 * Append a streamed output event to the current assistant turn.
 *
 * Each ``line`` arriving here is already the text extracted from a
 * stream-json event by the backend (see
 * ``_extract_stream_json_text``). For ``assistant`` events that's a
 * full block joined by newlines; concat without an inserted separator
 * so paragraph breaks come from the events themselves, not from our
 * line-stitching.
 */
session.onOutput((line: string) => {
  streamingContent.value += line;
  // The first chunk from claude clears the "thinking" indicator —
  // we're now actively rendering the response in a live bubble.
  awaitingResponse.value = false;
  if (diagnosticTimer) {
    clearTimeout(diagnosticTimer);
    diagnosticTimer = null;
  }
  diagnostic.value = null;
});

session.onComplete((status: string) => {
  // Finalize whatever's been streaming into a permanent assistant
  // bubble, then drop a small system note so the user can tell the
  // session has wound down.
  flushStreamingToMessage();
  awaitingResponse.value = false;
  if (diagnosticTimer) {
    clearTimeout(diagnosticTimer);
    diagnosticTimer = null;
  }
  diagnostic.value = null;
  messages.value.push({
    role: 'system',
    content: `Session ended (${status}).`,
    timestamp: new Date().toISOString(),
  });
});

session.onError((message: string) => {
  showToast(message, 'error');
});

function flushStreamingToMessage() {
  if (!streamingContent.value.trim()) {
    streamingContent.value = '';
    return;
  }
  messages.value.push({
    role: 'assistant',
    content: streamingContent.value,
    timestamp: new Date().toISOString(),
  });
  streamingContent.value = '';
}

async function handleSend() {
  const text = inputMessage.value.trim();
  if (!text) return;
  inputMessage.value = '';

  // If we have output in flight from the previous turn, lock it into
  // an assistant bubble before the user bubble lands — otherwise the
  // new user message appears above its own answer.
  flushStreamingToMessage();

  messages.value.push({
    role: 'user',
    content: text,
    timestamp: new Date().toISOString(),
  });

  if (!session.activeSessionId.value) {
    showToast('No active session — click Start first.', 'info');
    return;
  }
  awaitingResponse.value = true;
  if (diagnosticTimer) clearTimeout(diagnosticTimer);
  diagnosticTimer = setTimeout(() => {
    // No output 8s after send — surface a hint so the user knows
    // we're not just sitting on a spinner. Most claude responses
    // start streaming inside 2-3 seconds.
    if (awaitingResponse.value) {
      diagnostic.value =
        'No output yet from claude. If this hangs, the backend may need a restart to pick up v0.7.44 (pipe transport).';
    }
  }, 8000);
  await session.sendInput(text);
}

async function handleStart() {
  messages.value = [];
  streamingContent.value = '';
  awaitingResponse.value = false;
  diagnostic.value = null;
  if (diagnosticTimer) {
    clearTimeout(diagnosticTimer);
    diagnosticTimer = null;
  }
  await session.startSession({
    // ``--print`` + ``--input-format stream-json`` keeps claude alive
    // reading JSON events from stdin (the backend wraps the user's
    // text in the right envelope). ``--output-format stream-json``
    // makes it emit one JSON event per line on stdout — the backend's
    // stream-json parser converts that to clean prose before it
    // reaches us, so no TUI banner / ANSI escapes leak through.
    cmd: [
      'claude',
      '--print',
      '--input-format',
      'stream-json',
      '--output-format',
      'stream-json',
      '--verbose',
    ],
    execution_type: 'direct',
    execution_mode: 'interactive',
    stream_json: true,
    // ``claude --print`` refuses to read from a tty. The backend
    // honors ``use_pty: false`` by spawning via ``subprocess.Popen``
    // with anonymous pipes instead of ``pty.fork()``.
    use_pty: false,
  });
}

async function handleStop() {
  await session.stopSession();
}

onMounted(() => {
  session.loadSessions();
});

// useProjectSession's own onUnmounted resets stream/ralph/team state —
// no extra cleanup is needed here.

defineExpose({ session });
</script>

<template>
  <div class="grd-chat-view">
    <div class="header-bar">
      <div class="header-left">
        <h3 class="title">Interactive session</h3>
        <span class="subtitle">
          Backed by a real ``claude`` subprocess in this project's worktree
        </span>
      </div>
      <div class="header-actions">
        <button
          v-if="!hasActiveSession"
          class="btn btn-primary"
          :disabled="session.isLoading.value"
          @click="handleStart"
        >
          {{ session.isLoading.value ? 'Starting…' : 'Start session' }}
        </button>
        <button
          v-else
          class="btn btn-danger"
          @click="handleStop"
        >
          Stop
        </button>
      </div>
    </div>

    <AiChatPanelManaged
      class="chat-panel"
      :messages="messages"
      :is-processing="awaitingResponse"
      :streaming-content="streamingContent"
      :input-message="inputMessage"
      :read-only="!hasActiveSession"
      welcome-title="Start to begin"
      welcome-subtitle="Click Start to spawn an interactive Claude in this project's worktree. Type below to talk to it."
      :input-placeholder="hasActiveSession ? 'Type a message…' : 'Start a session first'"
      :hide-cli-runner-toggle="true"
      @update:input-message="inputMessage = $event"
      @send="handleSend"
    />

    <div v-if="diagnostic" class="diagnostic-banner">{{ diagnostic }}</div>

    <div v-if="session.error.value" class="error-banner">
      <span>{{ session.error.value }}</span>
      <button class="error-dismiss" @click="session.error.value = null">Dismiss</button>
    </div>
  </div>
</template>

<style scoped>
.grd-chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 500px;
  background: var(--bg-primary);
  border-radius: 8px;
  border: 1px solid var(--border-default);
  overflow: hidden;
}
.header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  gap: 12px;
}
.header-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.subtitle {
  font-size: 12px;
  color: var(--text-muted);
}
.header-actions {
  display: flex;
  gap: 8px;
}
.chat-panel {
  flex: 1;
  min-height: 0;
}
.diagnostic-banner {
  padding: 8px 16px;
  background: rgba(255, 200, 0, 0.08);
  border-top: 1px solid rgba(255, 200, 0, 0.4);
  font-size: 12px;
  color: var(--text-secondary);
}
.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: rgba(255, 85, 85, 0.1);
  border-top: 1px solid var(--accent-red);
  font-size: 13px;
  color: var(--accent-red);
}
.error-dismiss {
  background: transparent;
  border: 1px solid var(--accent-red);
  border-radius: 4px;
  color: var(--accent-red);
  font-size: 12px;
  padding: 2px 8px;
  cursor: pointer;
}
.error-dismiss:hover {
  background: var(--accent-red);
  color: #fff;
}
</style>
