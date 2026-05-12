<script setup lang="ts">
/**
 * Chat-style renderer on top of a GRD project session.
 *
 * The underlying transport is unchanged from ``ProjectSessionPanel`` —
 * still a PTY-backed subprocess managed by ``useProjectSession``,
 * still piping user input to stdin, still streaming stdout/stderr
 * lines back over SSE. What's different is the rendering: instead of
 * a monospace terminal block, output is accumulated into assistant
 * chat bubbles with proper markdown (lists, headings, code fences),
 * and user inputs render as user bubbles between turns.
 *
 * Why this exists vs. the SuperAgent playground:
 *   - GRD sessions still spawn arbitrary commands (claude, ralph_loop,
 *     team_spawn, etc.) — they're the right tool when you want a real
 *     subprocess that can talk to the filesystem and accept stdin.
 *   - But the *output* of a chat-like cmd (``claude`` in interactive
 *     REPL) is just text — there's no reason to render it as terminal
 *     output. Users said "I don't want to see terminal text in the
 *     GRD session"; this view answers that without abandoning the
 *     PTY model that the team-spawn / ralph-loop flows depend on.
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
const justSent = ref(''); // remember last user text for echo-strip

const hasActiveSession = computed(() => Boolean(session.activeSessionId.value));

/**
 * Append a streamed PTY output line to the current assistant turn.
 *
 * Heuristic: claude in interactive REPL echoes the user's input back
 * before its response (the tty echos stdin). If the first line after
 * a user send matches the user's text verbatim, swallow it so the
 * chat doesn't show the message twice.
 */
session.onOutput((line: string) => {
  if (justSent.value && line.trim() === justSent.value.trim()) {
    justSent.value = '';
    return;
  }
  // Preserve newlines between accumulated lines so marked.parse sees
  // them as paragraph breaks.
  streamingContent.value += (streamingContent.value ? '\n' : '') + line;
});

session.onComplete((status: string) => {
  // Finalize whatever's been streaming into a permanent assistant
  // bubble, then drop a small system note so the user can tell the
  // session has wound down.
  flushStreamingToMessage();
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
  justSent.value = text;

  if (!session.activeSessionId.value) {
    showToast('No active session — click Start first.', 'info');
    return;
  }
  await session.sendInput(text);
}

async function handleStart() {
  messages.value = [];
  streamingContent.value = '';
  await session.startSession({
    cmd: ['claude'],
    execution_type: 'direct',
    execution_mode: 'interactive',
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
      :is-processing="session.isStreaming.value"
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
