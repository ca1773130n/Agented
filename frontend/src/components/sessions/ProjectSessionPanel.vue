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
import SessionStartDialog from './SessionStartDialog.vue';
import InteractiveQuestionCard from './InteractiveQuestionCard.vue';
import type { AskUserQuestionItem } from '../../composables/useProjectSession';

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

// ``hydratedEmpty`` distinguishes "you clicked an old session that
// has no recorded transcript" from "you haven't started anything
// yet" — the AiChatPanelManaged default welcome screen reads weirdly
// in the first case ("AI will guide you through designing your ..."
// is template copy for an entity-creation flow we don't fit). v0.7.61.
const hydratedEmpty = ref(false);

// v0.7.63 — pending ``AskUserQuestion`` payload. Set when the backend
// emits an ``ask_user_question`` SSE event; cleared when the user
// answers (or Skip's). Rendered as an ``InteractiveQuestionCard``
// pinned below the chat panel.
const pendingQuestion = ref<{
  tool_use_id: string;
  questions: AskUserQuestionItem[];
} | null>(null);

// Soft diagnostic shown if no output arrives within 8s of sending a
// message. Most claude responses begin streaming within 2-3s, so 8s
// of silence is a useful tripwire — and a "backend may need a
// restart" hint catches the most common stuck-spinner case during
// rollout. (Migrated from GrdSessionChatView, which v0.7.55 drops.)
const diagnostic = ref<string | null>(null);
let diagnosticTimer: ReturnType<typeof setTimeout> | null = null;
function clearDiagnostic() {
  if (diagnosticTimer) {
    clearTimeout(diagnosticTimer);
    diagnosticTimer = null;
  }
  diagnostic.value = null;
}

// Active session object for status lookups
const activeSession = computed(() => {
  if (!session.activeSessionId.value) return null;
  return session.sessions.value.find((s) => s.id === session.activeSessionId.value) ?? null;
});

// Wire up callbacks
session.onOutput((line: string) => {
  if (isDirectMode.value) {
    // Claude's stream-json emits one ``assistant`` event per block —
    // a single logical turn often arrives as text + tool_use +
    // tool_use + text, four separate ``onOutput`` calls. Earlier
    // versions pushed each into its own bubble; the user pointed
    // out that a sequence of tool calls reads better as a single
    // grouped bubble.
    //
    // Strategy: when the last message in the list is already
    // ``assistant``, append to it with a paragraph break. Anything
    // else (no messages yet, or a user/system message in between)
    // starts a fresh bubble. This works the same way for live
    // streaming and for historical replay from ``log_json``.
    const last = messages.value[messages.value.length - 1];
    if (last && last.role === 'assistant') {
      last.content = last.content
        ? `${last.content}\n\n${line}`
        : line;
    } else {
      messages.value.push({
        role: 'assistant',
        content: line,
        timestamp: new Date().toISOString(),
      });
    }
    awaitingResponse.value = false;
    clearDiagnostic();
  } else {
    outputRef.value?.write(line + '\n');
  }
});

session.onComplete((status: string, _exitCode: number) => {
  awaitingResponse.value = false;
  clearDiagnostic();
  if (isDirectMode.value) {
    messages.value.push({
      role: 'system',
      content: `Session ended (${status}).`,
      timestamp: new Date().toISOString(),
    });
  } else {
    outputRef.value?.finalize();
    // Only ralph / team-spawn use the toast — direct-mode users
    // already see the system bubble inside the chat.
    const isSuccess = status === 'completed';
    showToast(
      `Session ${isSuccess ? 'completed' : 'ended'} (${status})`,
      isSuccess ? 'success' : 'info',
    );
  }
});

session.onError((message: string) => {
  showToast(message, 'error');
});

session.onAskUserQuestion((payload) => {
  // Setting pendingQuestion replaces any earlier question, which
  // matches the natural flow (claude only asks one at a time). The
  // ``awaitingResponse`` spinner stops since input now lives in the
  // card.
  pendingQuestion.value = payload;
  awaitingResponse.value = false;
  clearDiagnostic();
});

async function onQuestionAnswered(answers: Record<string, string | string[]>) {
  const pending = pendingQuestion.value;
  if (!pending) return;
  pendingQuestion.value = null;

  // Render a short summary user bubble so the chat reflects the
  // selection (full structured payload goes to claude's stdin via
  // the backend endpoint, which also persists it to log_json).
  const summary = Object.entries(answers)
    .map(([q, a]) => `**${q}** → ${Array.isArray(a) ? a.join(', ') : a}`)
    .join('\n\n');
  messages.value.push({
    role: 'user',
    content: summary,
    timestamp: new Date().toISOString(),
  });
  awaitingResponse.value = true;

  try {
    await grdApi.answerSessionQuestion(
      props.projectId,
      session.activeSessionId.value ?? '',
      pending.tool_use_id,
      answers,
    );
  } catch (err) {
    showToast(
      err instanceof Error ? err.message : 'Failed to send answer',
      'error',
    );
    awaitingResponse.value = false;
  }
}

function onQuestionSkipped() {
  pendingQuestion.value = null;
  // Skipping means we don't send a tool_result; claude will keep
  // waiting. A toast tells the user this is non-destructive.
  showToast(
    'Skipped — claude is still waiting. Reopen the question or stop the session.',
    'info',
  );
}

// Dialog visibility. ``handleStart`` (bound to the SessionControls
// Start button) opens it; ``onDialogConfirm`` performs the actual
// session create with the values the dialog collected.
const showStartDialog = ref(false);

function handleStart() {
  showStartDialog.value = true;
}

async function onDialogConfirm(payload: {
  name: string | null;
  autoTitle: boolean;
  yoloMode: boolean;
  executionType: 'direct' | 'ralph_loop' | 'team_spawn';
  accountId: string | null;
}) {
  showStartDialog.value = false;
  executionType.value = payload.executionType;

  outputRef.value?.reset();
  messages.value = [];
  awaitingResponse.value = false;
  inputMessage.value = '';
  hydratedEmpty.value = false;
  pendingQuestion.value = null;
  clearDiagnostic();

  const isDirect = payload.executionType === 'direct';
  const baseFields = {
    name: payload.name,
    auto_title: payload.autoTitle,
    yolo_mode: payload.yoloMode,
    // v0.7.58 — server requires account_id when yolo is off; passing
    // null/omitted in yolo is fine because the backend short-circuits
    // the whitelist check.
    ...(payload.accountId ? { account_id: payload.accountId } : {}),
  };
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
        ...baseFields,
      }
    : {
        cmd: ['claude'],
        execution_type: payload.executionType,
        execution_mode: 'interactive',
        ...baseFields,
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

    // Soft tripwire — if 8s pass with no output, surface a hint.
    // Cleared on the first ``onOutput`` chunk or on session
    // complete. The "backend may need a restart" line is here
    // because that's the single most common explanation when this
    // fires (a stale gunicorn process).
    clearDiagnostic();
    diagnosticTimer = setTimeout(() => {
      if (awaitingResponse.value) {
        diagnostic.value =
          'No output yet from claude. If this hangs, the backend may need a restart.';
      }
    }, 8000);
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
  pendingQuestion.value = null;
  session.switchSession(sessionId);

  // Hydrate chat history from the backend's persisted ``log_json``
  // before any new SSE output arrives, so clicking a session in
  // the sidebar reveals what was actually said (rather than the
  // empty welcome screen). For sessions whose subprocess has already
  // exited, this is the ONLY way to recover the conversation —
  // the in-memory ring buffer is gone.
  if (isDirectMode.value) {
    hydratedEmpty.value = false;
    try {
      const result = await grdApi.getSessionMessages(props.projectId, sessionId);
      const raw = result.messages ?? [];
      // Collapse consecutive same-role entries into grouped bubbles
      // for the same reason as the live ``onOutput`` path. Without
      // this, a turn with 4 tool calls comes back as 4 separate
      // bubbles instead of one.
      const grouped: ChatMsg[] = [];
      for (const m of raw) {
        const tail = grouped[grouped.length - 1];
        if (tail && tail.role === m.role) {
          tail.content = tail.content
            ? `${tail.content}\n\n${m.content}`
            : m.content;
        } else {
          grouped.push({ role: m.role, content: m.content, timestamp: m.ts });
        }
      }
      messages.value = grouped;
      // No transcript and the session is over → show a dedicated
      // empty state. (For active sessions, the ring buffer will
      // still stream live output so don't mark hydratedEmpty.)
      const sess = session.sessions.value.find((s) => s.id === sessionId);
      const isFinished = sess?.status === 'completed' || sess?.status === 'failed';
      hydratedEmpty.value = grouped.length === 0 && isFinished;
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
      <h3 class="panel-title">Interactive session</h3>
      <div class="header-actions">
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
              <span class="session-item-id">
                {{ s.name || truncateId(s.id) }}
                <span v-if="s.yolo_mode" class="yolo-badge" title="Yolo mode">YOLO</span>
              </span>
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
          >
            <template #welcome>
              <div v-if="hydratedEmpty" class="empty-historical">
                <p class="empty-historical-title">No recorded transcript</p>
                <p class="empty-historical-sub">
                  This session ended before chat persistence was enabled, so its
                  conversation can't be replayed. Start a new session to record one.
                </p>
              </div>
            </template>
          </AiChatPanelManaged>

          <!-- v0.7.63 — interactive ``AskUserQuestion`` widget. Shows
               only when claude is waiting on a structured answer;
               clears itself on submit / skip / Start. -->
          <InteractiveQuestionCard
            v-if="pendingQuestion && isDirectMode"
            :questions="pendingQuestion.questions"
            @confirm="onQuestionAnswered"
            @cancel="onQuestionSkipped"
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

    <!-- Soft "no output yet" hint after 8s of silence on a send. -->
    <div v-if="diagnostic" class="diagnostic-banner">{{ diagnostic }}</div>

    <!-- Error banner -->
    <div v-if="session.error.value" class="error-banner">
      <span>{{ session.error.value }}</span>
      <button class="error-dismiss" @click="session.error.value = null">Dismiss</button>
    </div>

    <SessionStartDialog
      :visible="showStartDialog"
      :project-id="projectId"
      @close="showStartDialog = false"
      @confirm="onDialogConfirm"
    />
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
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.yolo-badge {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(255, 100, 100, 0.15);
  color: var(--accent-red, #ff6464);
  border: 1px solid rgba(255, 100, 100, 0.3);
  text-transform: uppercase;
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

.empty-historical {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  text-align: center;
  gap: 8px;
  color: var(--text-secondary);
}
.empty-historical-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.empty-historical-sub {
  font-size: 13px;
  max-width: 360px;
  line-height: 1.5;
  margin: 0;
  color: var(--text-muted);
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
  transition: all 0.15s;
}

.error-dismiss:hover {
  background: var(--accent-red);
  color: #fff;
}
</style>
