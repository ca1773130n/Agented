<script setup lang="ts">
import { ref, toRef, onMounted, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { AiChatPanelManaged } from '@ai-accounts/vue-styled';
import { useProjectSession } from '../../composables/useProjectSession';
import { useToast } from '../../composables/useToast';
import { grdApi } from '../../services/api/grd';
import type { CreateSessionRequest } from '../../services/api/grd';
import SessionOutput from './SessionOutput.vue';
import SessionInput from './SessionInput.vue';
import SessionControls from './SessionControls.vue';
import SessionStartDialog from './SessionStartDialog.vue';
import SessionContextTray from './SessionContextTray.vue';
import ContextPreviewDrawer from './ContextPreviewDrawer.vue';
import GoalLoopStatusBanner from './GoalLoopStatusBanner.vue';
import InteractiveQuestionCard from './InteractiveQuestionCard.vue';
import PlanModeCard from './PlanModeCard.vue';
import PermissionPromptCard from './PermissionPromptCard.vue';
import type {
  AskUserQuestionItem,
  GoalIterationCompletedPayload,
  PermissionRequestPayload,
} from '../../composables/useProjectSession';
import type { ForgeAttachment } from '../../services/api/projects';

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
const executionType = ref<
  'direct' | 'ralph_loop' | 'team_spawn' | 'goal_loop'
>('direct');

// Direct-mode chat state. ``direct`` runs claude in stream-json so
// each ``onOutput`` line is already a complete assistant turn — render
// as proper chat bubbles (user vs assistant) instead of dumping into
// the terminal block. Ralph / team-spawn keep ``SessionOutput`` because
// their structured progress (iterations, team membership) reads
// better in monospace.
// v0.7.74 — true when the session uses the chat-style UI (chat
// bubbles + tray + AskUserQuestion card), as opposed to the
// monospace terminal output used by ralph/team. Both direct and
// goal_loop are stream-json chat sessions that should render the
// chat panel.
const isDirectMode = computed(
  () => executionType.value === 'direct' || executionType.value === 'goal_loop',
);
const messages = ref<ChatMsg[]>([]);
const inputMessage = ref('');
// v0.7.70 — per-prompt attachments (files / snippets / URLs /
// entity refs) collected by SessionContextTray. Sent alongside
// ``text`` on the next ``sendInput`` call, then cleared. Sticky
// across re-edits of the same draft, cleared on send or on session
// switch.
const pendingAttachments = ref<ForgeAttachment[]>([]);
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

// v0.7.65 — claude's ``ExitPlanMode`` payload. Distinct from
// pendingQuestion because the UX is approve/decline rather than
// multi-option selection.
const pendingPlan = ref<{ tool_use_id: string; plan: string } | null>(null);

// v0.7.69 — interactive PreToolUse permission prompt. The hook
// inside the claude subprocess is blocked waiting for our
// answer-permission-prompt endpoint. Different prompts can queue
// up if claude's tool calls are dispatched faster than the user
// can click, so this is an array, not a single ref.
const pendingPermissions = ref<PermissionRequestPayload[]>([]);

// v0.7.74 — goal-loop live state. Populated by SSE handlers fed
// from useProjectSession. Reset on session switch / start.
const goalLoopState = ref<{
  goal: string;
  iteration: number;
  maxIterations: number;
  lastVerdict: GoalIterationCompletedPayload | null;
  endedReason: string | null;
  endedDetail: string | null;
  judging: boolean;
} | null>(null);
const isGoalLoopMode = computed(
  () => executionType.value === 'goal_loop' && goalLoopState.value !== null,
);

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

// v0.7.67 — token-level streaming. ``output_delta`` events arrive
// per-token from claude's ``--include-partial-messages`` mode and
// should append to the live assistant bubble without any separator
// (otherwise "Hello world" becomes "Hello\n\nworld"). Backend
// guarantees the trailing ``assistant`` event's text is suppressed
// so we never double-render.
session.onOutputDelta((delta: string) => {
  if (!isDirectMode.value) return;
  const last = messages.value[messages.value.length - 1];
  if (last && last.role === 'assistant') {
    last.content = last.content + delta;
  } else {
    messages.value.push({
      role: 'assistant',
      content: delta,
      timestamp: new Date().toISOString(),
    });
  }
  awaitingResponse.value = false;
  clearDiagnostic();
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

session.onExitPlanMode((payload) => {
  pendingPlan.value = payload;
  awaitingResponse.value = false;
  clearDiagnostic();
});

session.onPermissionRequest((payload) => {
  // Park the request in the queue. The card renders the first
  // entry; once the user clicks Allow/Deny we shift it off and the
  // next one (if any) becomes visible.
  pendingPermissions.value = [...pendingPermissions.value, payload];
  // Don't ``awaitingResponse = false`` here — claude IS technically
  // still working (its hook is blocked on us). Spinner stays.
});

async function resolvePermission(decision: 'allow' | 'deny') {
  const head = pendingPermissions.value[0];
  if (!head) return;
  // Drop the request from the queue optimistically; the parked hook
  // will unblock on the server side once the POST lands.
  pendingPermissions.value = pendingPermissions.value.slice(1);
  // Push a small system bubble so the chat reflects the decision.
  messages.value.push({
    role: 'system',
    content:
      decision === 'allow'
        ? `<div class="hook-badge hook-badge--allow"><span class="hook-icon">🛡</span> <span class="hook-event">APPROVED</span> <span class="hook-tool">${head.tool_name}</span></div>`
        : `<div class="hook-badge hook-badge--deny"><span class="hook-icon">🛡</span> <span class="hook-event">DENIED</span> <span class="hook-tool">${head.tool_name}</span></div>`,
    timestamp: new Date().toISOString(),
  });
  try {
    await grdApi.answerPermissionPrompt(
      props.projectId,
      session.activeSessionId.value ?? '',
      head.request_id,
      decision,
    );
  } catch (err) {
    showToast(
      err instanceof Error ? err.message : 'Failed to send permission decision',
      'error',
    );
  }
}

session.onThinking((text: string) => {
  // v0.7.68 — surface claude's extended-thinking reasoning as a
  // collapsed-by-default disclosure widget. ChatBubble's marked +
  // DOMPurify pipeline preserves the ``<details>`` element; styling
  // lives in App.vue's global CSS so it crosses ``v-html``.
  const escape = (s: string) =>
    s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  const html =
    '<details class="thinking-block">' +
    '<summary>💭 Thinking</summary>' +
    `<pre class="thinking-body">${escape(text)}</pre>` +
    '</details>';
  messages.value.push({
    role: 'system',
    content: html,
    timestamp: new Date().toISOString(),
  });
});

session.onHookDecision((payload) => {
  // Render the hook decision as a system message containing a small
  // HTML badge. ChatBubble's marked + DOMPurify pipeline preserves
  // the markup; styling lives in App.vue's global CSS so it reaches
  // inside the v-html-rendered subtree.
  const escape = (s: string) =>
    s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');

  const decisionKind = payload.decision; // allow | deny | ask
  const tool = escape(payload.tool_name || 'tool');
  const hookEv = escape(payload.hook_event || 'Hook');
  // Show the first meaningful arg from the tool input so a Bash hook
  // says "ls /tmp" not just "Bash".
  const inp = payload.tool_input || {};
  const detailRaw = (
    (inp as Record<string, unknown>).command ||
    (inp as Record<string, unknown>).file_path ||
    (inp as Record<string, unknown>).path ||
    (inp as Record<string, unknown>).pattern ||
    ''
  ) as string;
  const detail = detailRaw ? `<code class="hook-arg">${escape(detailRaw)}</code>` : '';
  const html =
    `<div class="hook-badge hook-badge--${decisionKind}">` +
    `<span class="hook-icon" aria-hidden="true">🛡</span>` +
    `<span class="hook-event">${hookEv}</span>` +
    `<span class="hook-tool">${tool}</span>` +
    detail +
    `<span class="hook-decision">${decisionKind}</span>` +
    `</div>`;

  messages.value.push({
    role: 'system',
    content: html,
    timestamp: new Date().toISOString(),
  });
});

// v0.7.74 — goal-loop SSE handlers. Banner state lives on the panel
// so it survives across session switches via reset-on-confirm.
session.onGoalIterationStarted((payload) => {
  if (!goalLoopState.value) return;
  goalLoopState.value.iteration = payload.iteration;
  goalLoopState.value.maxIterations = payload.max_iterations;
  goalLoopState.value.judging = true;
});

session.onGoalIterationCompleted((payload) => {
  if (!goalLoopState.value) return;
  goalLoopState.value.lastVerdict = payload;
  goalLoopState.value.judging = false;
});

session.onGoalLoopEnded((payload) => {
  if (!goalLoopState.value) return;
  goalLoopState.value.endedReason = payload.reason;
  goalLoopState.value.endedDetail = payload.detail;
  goalLoopState.value.judging = false;
});

session.onGoalCheckDisagreement((payload) => {
  // Surface as a system message so the operator sees the warning
  // inline — the loop continues, so no banner state change.
  messages.value.push({
    role: 'system',
    content:
      `**Goal check disagreement** at iter ${payload.iteration} ` +
      `(streak ${payload.streak}): ` +
      `deterministic says not met (${payload.deterministic_reason}); ` +
      `LLM sanity check says met (${payload.llm_reason}). ` +
      `Loop continuing on deterministic verdict — stop manually if ` +
      `the LLM is right.`,
    timestamp: new Date().toISOString(),
  });
});

async function onPlanApprove() {
  const pending = pendingPlan.value;
  if (!pending) return;
  pendingPlan.value = null;
  messages.value.push({
    role: 'user',
    content: '**Plan decision** → Approved, proceeding with execution.',
    timestamp: new Date().toISOString(),
  });
  awaitingResponse.value = true;
  try {
    await grdApi.answerSessionPlan(
      props.projectId,
      session.activeSessionId.value ?? '',
      pending.tool_use_id,
      true,
    );
  } catch (err) {
    showToast(
      err instanceof Error ? err.message : 'Failed to approve plan',
      'error',
    );
    awaitingResponse.value = false;
  }
}

async function onPlanKeepPlanning() {
  const pending = pendingPlan.value;
  if (!pending) return;
  pendingPlan.value = null;
  messages.value.push({
    role: 'user',
    content: '**Plan decision** → Keep planning (do not execute yet).',
    timestamp: new Date().toISOString(),
  });
  awaitingResponse.value = true;
  try {
    await grdApi.answerSessionPlan(
      props.projectId,
      session.activeSessionId.value ?? '',
      pending.tool_use_id,
      false,
    );
  } catch (err) {
    showToast(
      err instanceof Error ? err.message : 'Failed to send plan decision',
      'error',
    );
    awaitingResponse.value = false;
  }
}

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
// v0.7.75 — slide-over preview of the compiled forge context.
// Operator clicks "Preview" in the tray; we pass the current
// pending attachments through so the preview matches what would
// actually go on the wire on send.
const showContextPreview = ref(false);

function handleStart() {
  showStartDialog.value = true;
}

function onPreviewContext() {
  showContextPreview.value = true;
}

async function onDialogConfirm(payload: {
  name: string | null;
  autoTitle: boolean;
  yoloMode: boolean;
  executionType: 'direct' | 'ralph_loop' | 'team_spawn' | 'goal_loop';
  accountId: string | null;
  // v0.7.73 — dialog payload now carries Forge picks too.
  forgeOverrides?: {
    disabled_binding_ids: number[];
    additions: Array<{
      kind: 'rule' | 'skill' | 'hook' | 'command' | 'mcp_server' | 'plugin';
      asset_id: string;
      role?: string | null;
    }>;
  };
  firstPromptAttachments?: ForgeAttachment[];
  // v0.7.74 — only populated when executionType === 'goal_loop'.
  goalLoopConfig?: {
    goal: string;
    checkCmd: string | null;
    maxIterations: number;
    maxWallSeconds: number;
    judgeBackendKind: 'claude' | 'codex' | 'gemini' | 'opencode';
    judgeModelOverride: string | null;
    // v0.7.87 — Ouroboros mode flag. Defaults to ``true`` on the
    // backend (per goal_loop_runner.py:264). The dialog exposes
    // it as an explicit toggle so the operator can opt out for
    // sessions where the agent backend is a poor fit for
    // structured hypothesis emission.
    ouroboros?: boolean;
  } | null;
}) {
  showStartDialog.value = false;
  executionType.value = payload.executionType;

  outputRef.value?.reset();
  messages.value = [];
  awaitingResponse.value = false;
  inputMessage.value = '';
  hydratedEmpty.value = false;
  pendingQuestion.value = null;
  pendingPlan.value = null;
  pendingPermissions.value = [];
  clearDiagnostic();

  // v0.7.73 — first-prompt attachments wait in pendingAttachments
  // until the operator types the first message and hits send. The
  // server-side compile happens then via /sessions/{sid}/input,
  // not at create_session (chat sessions read user content from
  // stdin in stream-json mode, so per-prompt context can't ride
  // the spawn argv).
  pendingAttachments.value = payload.firstPromptAttachments ?? [];

  // v0.7.74 — seed the goal-loop banner state when a goal_loop
  // session is starting; clear it otherwise. The state is the
  // banner's source of truth, fed live by SSE handlers as the
  // runner iterates.
  goalLoopState.value =
    payload.executionType === 'goal_loop' && payload.goalLoopConfig
      ? {
          goal: payload.goalLoopConfig.goal,
          iteration: 0,
          maxIterations: payload.goalLoopConfig.maxIterations,
          lastVerdict: null,
          endedReason: null,
          endedDetail: null,
          judging: false,
        }
      : null;

  // v0.7.74 — goal_loop uses the same stream-json command shape as
  // direct (the handler pumps continue prompts via the existing
  // input route, which requires --input-format stream-json). Treat
  // both as "chat-style" for cmd-building purposes.
  const isDirect =
    payload.executionType === 'direct' || payload.executionType === 'goal_loop';
  const baseFields = {
    name: payload.name,
    auto_title: payload.autoTitle,
    yolo_mode: payload.yoloMode,
    // v0.7.58 — server requires account_id when yolo is off; passing
    // null/omitted in yolo is fine because the backend short-circuits
    // the whitelist check.
    ...(payload.accountId ? { account_id: payload.accountId } : {}),
    // v0.7.73 — Forge bindings opt-outs + session-only additions.
    // The bundle compiles into --append-system-prompt for claude
    // and the overlay materialization for hooks/commands/MCP. We
    // only forward when there's at least one override so the
    // request body stays empty in the common "use project defaults
    // as-is" case.
    ...(payload.forgeOverrides &&
    (payload.forgeOverrides.disabled_binding_ids.length > 0 ||
      payload.forgeOverrides.additions.length > 0)
      ? {
          forge_context: {
            session_overrides: payload.forgeOverrides,
          },
        }
      : {}),
    // v0.7.74 — goal loop only ships the config when the dialog
    // actually picked the goal_loop type. Server-side handler
    // routing is based on execution_type alone, so this is just
    // payload tidiness.
    ...(payload.executionType === 'goal_loop' && payload.goalLoopConfig
      ? {
          goal_loop_config: {
            goal: payload.goalLoopConfig.goal,
            check_cmd: payload.goalLoopConfig.checkCmd,
            max_iterations: payload.goalLoopConfig.maxIterations,
            max_wall_seconds: payload.goalLoopConfig.maxWallSeconds,
            judge_backend_kind: payload.goalLoopConfig.judgeBackendKind,
            judge_model_override: payload.goalLoopConfig.judgeModelOverride,
            // v0.7.87 (codex WARN A) — forward the Ouroboros flag
            // when the dialog set it (true or false). Omitting
            // the key entirely also yields the backend default
            // (true), so an undefined value here doesn't change
            // behaviour — but sending the explicit value keeps
            // the audit trail clear when reading the session's
            // ``goal_loop_config`` JSON.
            ...(payload.goalLoopConfig.ouroboros !== undefined
              ? { ouroboros: payload.goalLoopConfig.ouroboros }
              : {}),
          },
        }
      : {}),
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
          // v0.7.66 — pass through PreToolUse / PostToolUse hook
          // lifecycle events so the chat can surface read-only
          // permission decision badges. The backend filters
          // hook noise (hook_started, etc.) and only emits a
          // structured ``hook_decision`` event when a hook returns
          // a permission decision.
          '--include-hook-events',
          // v0.7.67 — stream text token-by-token so the chat bubble
          // fills in live. Backend dedups: when deltas have
          // streamed, the trailing ``assistant`` event's text
          // blocks are dropped so we don't double-render.
          '--include-partial-messages',
        ],
        // ``execution_type`` MUST reflect the user's pick so the
        // server routes to the right handler — direct vs goal_loop
        // differ only in the loop driver, not the cmd shape.
        execution_type: payload.executionType,
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
  // v0.7.70 — capture the current attachments at submit time so the
  // chips clear after the send (operator's mental model: "I attach,
  // I send, the tray empties for the next turn"). Re-editing the
  // input is fine; the chips stay until send.
  const attachments = pendingAttachments.value.slice();
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
  session.sendInput(
    text,
    attachments.length > 0 ? (attachments as unknown as Array<Record<string, unknown>>) : undefined,
  );
  pendingAttachments.value = [];
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
  pendingPlan.value = null;
  pendingPermissions.value = [];
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

// v0.7.95 — when arriving via deep-link with ``?sessionId=…``
// (currently used by the SA inspector's "Recent Ouroboros runs"
// panel), select that session as soon as the list resolves so
// the operator lands directly on the requested run instead of an
// arbitrary default.
const route = useRoute();
const router = useRouter();

async function applyDeepLinkSession() {
  const target = route.query.sessionId;
  if (typeof target !== 'string' || !target) return;
  // Wait for the sessions list to include the deep-linked id —
  // otherwise switchSession would try to attach to a session the
  // composable hasn't loaded yet.
  const exists = session.sessions.value.some(s => s.id === target);
  if (!exists) return;
  await handleSessionClick(target);
  // Strip the query so a manual refresh doesn't keep re-selecting
  // the same session forever (and so subsequent user clicks aren't
  // overridden on every route nav).
  const { sessionId: _drop, ...rest } = route.query;
  router.replace({ query: rest });
}

onMounted(async () => {
  await session.loadSessions();
  await applyDeepLinkSession();
});

watch(
  () => route.query.sessionId,
  () => {
    applyDeepLinkSession();
  },
);
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

          <!-- v0.7.74 — live banner for goal-loop sessions. Shows
               goal text, iteration counter, and the last judge
               verdict. Hides once the loop ends with a terminal
               status. -->
          <GoalLoopStatusBanner
            v-if="isGoalLoopMode && goalLoopState"
            :goal="goalLoopState.goal"
            :iteration="goalLoopState.iteration"
            :max-iterations="goalLoopState.maxIterations"
            :last-verdict="goalLoopState.lastVerdict"
            :ended-reason="goalLoopState.endedReason"
            :ended-detail="goalLoopState.endedDetail"
            :judging="goalLoopState.judging"
          />

          <!-- v0.7.63 — interactive ``AskUserQuestion`` widget. Shows
               only when claude is waiting on a structured answer;
               clears itself on submit / skip / Start. -->
          <InteractiveQuestionCard
            v-if="pendingQuestion && isDirectMode"
            :questions="pendingQuestion.questions"
            @confirm="onQuestionAnswered"
            @cancel="onQuestionSkipped"
          />

          <!-- v0.7.65 — ``ExitPlanMode`` proposal. Claude wrote out a
               plan in plan mode and is waiting for approval before
               executing. -->
          <PlanModeCard
            v-if="pendingPlan && isDirectMode"
            :plan="pendingPlan.plan"
            @approve="onPlanApprove"
            @keep-planning="onPlanKeepPlanning"
          />

          <!-- v0.7.69 — interactive permission prompt. Claude's
               PreToolUse hook is blocked on our backend until the
               user clicks Approve / Deny. Queue head renders here. -->
          <PermissionPromptCard
            v-if="pendingPermissions.length > 0 && isDirectMode"
            :request="pendingPermissions[0]"
            @allow="resolvePermission('allow')"
            @deny="resolvePermission('deny')"
          />

          <!-- v0.7.70 — per-prompt context tray. Sits above the chat
               input in direct mode so the operator can attach files /
               snippets / URLs / entity refs before sending. Tray
               clears on send. For ralph/team sessions we don't
               render it because the autonomous loop owns its own
               turn structure. -->
          <!-- Disabled only when there's no active session at all.
               During the idle "waiting for next prompt" window the
               tray must remain enabled so the operator can prep
               attachments before clicking send. ``isStreaming`` would
               be the wrong guard here: chips are local state and
               don't talk to the stream until send time. -->
          <SessionContextTray
            v-if="isDirectMode"
            v-model:attachments="pendingAttachments"
            :disabled="!session.activeSessionId.value"
            @preview-context="onPreviewContext"
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

    <!-- v0.7.75 — slide-over preview of the compiled forge
         context. Reads the same backend endpoint
         (``/forge-context/preview``) the session would hit on
         send, so what the operator sees is what claude gets. -->
    <ContextPreviewDrawer
      :open="showContextPreview"
      :project-id="projectId"
      :attachments="pendingAttachments"
      @close="showContextPreview = false"
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
