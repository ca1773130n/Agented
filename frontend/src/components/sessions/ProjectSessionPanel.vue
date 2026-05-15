<script setup lang="ts">
import { ref, toRef, onMounted, computed } from 'vue';
import { AiChatPanelManaged } from '@ai-accounts/vue-styled';
import { useProjectSession } from '../../composables/useProjectSession';
import { useToast } from '../../composables/useToast';
import { grdApi } from '../../services/api/grd';
import type { CreateSessionRequest } from '../../services/api/grd';
import SessionOutput from './SessionOutput.vue';
import SessionInput from './SessionInput.vue';
import SessionControls from './SessionControls.vue';
import ExecutionTypeSelector from './ExecutionTypeSelector.vue';

interface ChatMsg {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
}

const props = defineProps<{
  projectId: string;
}>();

const showToast = useToast();
const session = useProjectSession(toRef(props, 'projectId'));

const outputRef = ref<InstanceType<typeof SessionOutput> | null>(null);
const executionType = ref<'direct' | 'ralph_loop' | 'team_spawn'>('direct');

// Direct-mode chat state. ``direct`` runs claude in stream-json so
// each ``onOutput`` line is already a complete assistant turn — render
// as proper chat bubbles (user vs assistant) instead of dumping into
// the terminal block. Ralph / team-spawn keep ``SessionOutput`` because
// their structured progress (iterations, team membership) reads
// better in monospace.
const isDirectMode = computed(() => executionType.value === 'direct');
const messages = ref<ChatMsg[]>([]);
const inputMessage = ref('');
const awaitingResponse = ref(false);

// Active session object for status lookups
const activeSession = computed(() => {
  if (!session.activeSessionId.value) return null;
  return session.sessions.value.find((s) => s.id === session.activeSessionId.value) ?? null;
});

// Wire up callbacks
session.onOutput((line: string) => {
  if (isDirectMode.value) {
    // Each line is a full assistant turn (stream-json without
    // ``--include-partial-messages``); push straight into messages
    // so the bubble persists.
    messages.value.push({
      role: 'assistant',
      content: line,
      timestamp: new Date().toISOString(),
    });
    awaitingResponse.value = false;
  } else {
    outputRef.value?.write(line + '\n');
  }
});

session.onComplete((status: string, _exitCode: number) => {
  awaitingResponse.value = false;
  if (isDirectMode.value) {
    messages.value.push({
      role: 'system',
      content: `Session ended (${status}).`,
      timestamp: new Date().toISOString(),
    });
  } else {
    outputRef.value?.finalize();
  }
  const isSuccess = status === 'completed';
  showToast(
    `Session ${isSuccess ? 'completed' : 'ended'} (${status})`,
    isSuccess ? 'success' : 'info',
  );
});

session.onError((message: string) => {
  showToast(message, 'error');
});

async function handleStart() {
  outputRef.value?.reset();
  messages.value = [];
  awaitingResponse.value = false;
  inputMessage.value = '';
  // Direct mode runs claude in stream-json over a pipe transport — same
  // plumbing as ``GrdSessionChatView``. This is what restores markdown
  // rendering in ``SessionOutput``'s streaming parser: claude emits
  // structured assistant events, the backend's stream-json parser lifts
  // out clean prose / tool-use blocks, and ``write(line + '\n')``
  // hands that to the markdown parser.
  //
  // History: v0.7.41 changed the cmd from ``claude -p 'You are in an
  // interactive session'`` to bare ``claude`` to fix a Connection-lost
  // bug — but that switched claude into its interactive TUI, which
  // ``SessionOutput``'s markdown parser can't render (box-drawing
  // chars, cursor escapes). The right answer was always stream-json
  // (which didn't exist on this code path yet at the time). v0.7.49
  // closes the loop.
  //
  // For ralph_loop / team_spawn, leave the cmd alone — those paths
  // route through dedicated backend handlers that construct their own
  // commands and don't need stream-json.
  const isDirect = executionType.value === 'direct';
  const request: CreateSessionRequest = isDirect
    ? {
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
        use_pty: false,
      }
    : {
        cmd: ['claude'],
        execution_type: executionType.value,
        execution_mode: 'interactive',
      };
  await session.startSession(request);
}

function handleSend(text: string) {
  if (isDirectMode.value) {
    // Echo the user's message into the chat as a user bubble before
    // we ship it. The previous behavior only rendered claude's
    // replies, which made the panel look like a monologue.
    messages.value.push({
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    });
    awaitingResponse.value = true;
    inputMessage.value = '';
  }
  session.sendInput(text);
}

// AiChatPanelManaged emits ``send`` with no args — it uses the
// bound ``input-message`` value internally. Wrap our send so both
// SessionInput (which passes text) and the chat panel (which uses
// inputMessage state) hit the same code path.
function handleChatSend() {
  const text = inputMessage.value.trim();
  if (!text) return;
  handleSend(text);
}

function handleChatKeydown(event: KeyboardEvent) {
  // Enter sends; Shift+Enter inserts a newline. IME composition
  // (Korean / Japanese / Chinese) is preserved so pressing Enter to
  // commit a composition doesn't accidentally submit.
  if (
    event.key === 'Enter' &&
    !event.shiftKey &&
    !event.isComposing &&
    event.keyCode !== 229
  ) {
    event.preventDefault();
    handleChatSend();
  }
}

async function handleSessionClick(sessionId: string) {
  outputRef.value?.reset();
  messages.value = [];
  awaitingResponse.value = false;
  session.switchSession(sessionId);

  // Hydrate chat history from the backend's persisted ``log_json``
  // before any new SSE output arrives, so clicking a session in
  // the sidebar reveals what was actually said (rather than the
  // empty welcome screen). For sessions whose subprocess has already
  // exited, this is the ONLY way to recover the conversation —
  // the in-memory ring buffer is gone.
  if (isDirectMode.value) {
    try {
      const result = await grdApi.getSessionMessages(props.projectId, sessionId);
      messages.value = (result.messages ?? []).map((m) => ({
        role: m.role,
        content: m.content,
        timestamp: m.ts,
      }));
    } catch {
      // Quiet — empty messages is the worst case, not a hard error.
    }
  }
}

function statusColor(status: string): string {
  switch (status) {
    case 'active':
      return 'var(--accent-green)';
    case 'paused':
      return 'var(--accent-yellow)';
    case 'failed':
      return 'var(--accent-red)';
    default:
      return 'var(--text-muted)';
  }
}

function truncateId(id: string): string {
  if (id.length <= 12) return id;
  return id.slice(0, 12) + '...';
}

onMounted(() => {
  session.loadSessions();
});
</script>

<template>
  <div class="session-panel">
    <!-- Header bar -->
    <div class="panel-header">
      <h3 class="panel-title">Sessions</h3>
      <div class="header-actions">
        <ExecutionTypeSelector v-model="executionType" />
        <SessionControls
          :session-status="activeSession?.status ?? null"
          :is-streaming="session.isStreaming.value"
          @start="handleStart"
          @pause="session.pauseSession"
          @resume="session.resumeSession"
          @stop="session.stopSession"
        />
      </div>
    </div>

    <div class="panel-body">
      <!-- Session list sidebar -->
      <aside class="session-sidebar">
        <div class="sidebar-header">
          <span class="sidebar-label">History</span>
          <span class="session-count">{{ session.sessions.value.length }}</span>
        </div>
        <div class="session-list">
          <button
            v-for="s in session.sessions.value"
            :key="s.id"
            class="session-item"
            :class="{ active: s.id === session.activeSessionId.value }"
            @click="handleSessionClick(s.id)"
          >
            <span class="status-dot" :style="{ background: statusColor(s.status) }"></span>
            <div class="session-item-info">
              <span class="session-item-id">{{ truncateId(s.id) }}</span>
              <span class="session-item-type">{{ s.execution_type }}</span>
            </div>
          </button>
          <div v-if="session.sessions.value.length === 0" class="sidebar-empty">
            No sessions yet
          </div>
        </div>
      </aside>

      <!-- Main content area -->
      <div class="session-main">
        <template v-if="session.activeSessionId.value">
          <!-- Direct mode renders proper chat bubbles so the user's
               prompt is visible alongside claude's responses. -->
          <AiChatPanelManaged
            v-if="isDirectMode"
            class="chat-panel"
            :messages="messages"
            :is-processing="awaitingResponse"
            :input-message="inputMessage"
            input-placeholder="Type a message…"
            :hide-cli-runner-toggle="true"
            @update:input-message="inputMessage = $event"
            @send="handleChatSend"
            @keydown="handleChatKeydown"
          />
          <!-- Ralph loops / team spawn keep the monospace terminal so
               structured progress events (iteration counters, team
               membership tables) read cleanly. -->
          <template v-else>
            <SessionOutput ref="outputRef" />
            <SessionInput
              :disabled="!session.isStreaming.value"
              @send="handleSend"
            />
          </template>
        </template>
        <div v-else class="empty-state">
          <div class="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="2" y="3" width="20" height="14" rx="2" />
              <path d="M8 21h8" />
              <path d="M12 17v4" />
              <path d="M7 8h3" />
            </svg>
          </div>
          <p class="empty-title">Select or start a session</p>
          <p class="empty-sub">Choose a session from the sidebar or create a new one to begin.</p>
        </div>
      </div>
    </div>

    <!-- Error banner -->
    <div v-if="session.error.value" class="error-banner">
      <span>{{ session.error.value }}</span>
      <button class="error-dismiss" @click="session.error.value = null">Dismiss</button>
    </div>
  </div>
</template>

<style scoped>
.session-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 500px;
  background: var(--bg-primary);
  border-radius: 8px;
  border: 1px solid var(--border-default);
  overflow: hidden;
}

/* Header */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* Body: sidebar + main */
.panel-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* Sidebar */
.session-sidebar {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-default);
}

.sidebar-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}

.session-count {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 8px;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.12s;
  text-align: left;
}

.session-item:hover {
  background: var(--bg-tertiary);
}

.session-item.active {
  background: var(--bg-tertiary);
  outline: 1px solid var(--accent-cyan);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.session-item-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.session-item-id {
  font-size: 12px;
  font-family: 'Geist Mono', monospace;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-item-type {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.sidebar-empty {
  padding: 20px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}

/* Main content */
.session-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.chat-panel {
  flex: 1;
  min-height: 0;
}

/* Empty state */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
}

.empty-icon {
  width: 64px;
  height: 64px;
  background: var(--bg-tertiary);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
}

.empty-icon svg {
  width: 32px;
  height: 32px;
  color: var(--text-muted);
}

.empty-title {
  margin: 0 0 6px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-sub {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  max-width: 260px;
}

/* Error banner */
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
  transition: all 0.15s;
}

.error-dismiss:hover {
  background: var(--accent-red);
  color: #fff;
}
</style>
