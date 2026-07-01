import { ref, onUnmounted, type Ref } from 'vue';
import {
  grdApi,
  type GrdSession,
  type CreateSessionRequest,
  type RalphConfig,
  type TeamConfig,
} from '../services/api/grd';
import { useEventSource } from './useEventSource';
import type { PolicyAskEvent } from '../services/api';

// [08.L1] DEV-only diagnostic logger. Prod must not log raw SSE `event.data`
// payloads; in development these parse-failure warnings remain visible.
function warnParse(...args: unknown[]): void {
  if (import.meta.env.DEV) {
    console.warn(...args);
  }
}

// v0.7.63 — shape of one ``AskUserQuestion`` entry as emitted by
// claude's stream-json. ``options`` may also carry ``preview`` and
// ``annotations`` fields; we treat them as opaque ``unknown`` here
// so the renderer can adopt them later without an API break.
export interface AskUserQuestionOption {
  label: string;
  description?: string;
  preview?: string;
}
export interface AskUserQuestionItem {
  question: string;
  header?: string;
  multiSelect?: boolean;
  options: AskUserQuestionOption[];
}

// v0.7.66 — payload for the read-only hook decision badge.
export interface HookDecisionPayload {
  hook_event: string | null; // PreToolUse | PostToolUse | …
  hook_name: string | null;
  tool_name: string;
  tool_input: Record<string, unknown>;
  decision: 'allow' | 'deny' | 'ask';
  outcome: string | null; // success | failure
}

// v0.7.69 — interactive permission prompt: pause-and-ask the user
// before claude runs a tool. ``request_id`` is the registry key
// used when calling ``answerPermissionPrompt``.
export interface PermissionRequestPayload {
  request_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  cwd: string | null;
}

// v0.7.74 — goal-loop SSE payloads.
export interface GoalIterationCompletedPayload {
  iteration: number;
  verdict: 'met' | 'not_met';
  reason: string;
  source: 'deterministic' | 'llm' | 'cap';
}

export interface GoalCheckDisagreementPayload {
  iteration: number;
  deterministic_reason: string;
  llm_reason: string;
  streak: number;
}

/**
 * Composable for managing project session lifecycle, SSE streaming,
 * and session CRUD operations.
 *
 * Follows the same patterns as useAiChat.ts but tailored for PTY-based
 * project sessions with output/complete/error SSE events.
 *
 * SSE connection lifecycle is delegated to useEventSource.
 */
export function useProjectSession(projectId: Ref<string>) {
  // Public state
  const sessions = ref<GrdSession[]>([]);
  const activeSessionId = ref<string | null>(null);
  const isStreaming = ref(false);
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  // Ralph loop state
  const ralphState = ref<{
    iteration: number;
    maxIterations: number;
    circuitBreakerTriggered: boolean;
  } | null>(null);

  // Team spawn state
  const teamState = ref<{
    teamName: string | null;
    members: Array<{ name: string; agentId: string; agentType: string }>;
    tasks: Array<{ id: string; subject: string; status: string; owner?: string }>;
  } | null>(null);

  // Unified-loop control state (SP3). The loop is held at the iteration
  // boundary while ``paused``; ``awaitingHuman`` is true while the runner
  // is blocked on a human-gate checkpoint, with ``gateReason`` describing
  // why (e.g. "every 2 iterations" / "completion (met)").
  const paused = ref(false);
  const awaitingHuman = ref(false);
  const gateReason = ref<string | null>(null);

  // Private state
  let errorCount = 0;

  // Callback registrations
  let onOutputCb: ((line: string) => void) | undefined;
  // v0.7.67 — per-token text deltas (when --include-partial-messages
  // is on). Frontend appends to the live bubble without separators,
  // giving the same word-by-word streaming feel as the TUI.
  let onOutputDeltaCb: ((delta: string) => void) | undefined;
  let onCompleteCb:
    | ((status: string, exitCode: number, meta?: { backend?: string; model?: string }) => void)
    | undefined;
  let onErrorCb: ((message: string) => void) | undefined;
  // v0.7.63 — claude's ``AskUserQuestion`` tool surfaces here as a
  // structured payload (the backend splits it off the regular output
  // bubble). Panels register a handler to render clickable options.
  let onAskUserQuestionCb:
    | ((payload: { tool_use_id: string; questions: AskUserQuestionItem[] }) => void)
    | undefined;
  // v0.7.65 — ``ExitPlanMode``: claude is asking the user to approve
  // a plan before execution. Payload carries the plan markdown and
  // the tool_use_id for the answer round-trip.
  let onExitPlanModeCb:
    | ((payload: { tool_use_id: string; plan: string }) => void)
    | undefined;
  // v0.7.66 — read-only ``PreToolUse``/``PostToolUse`` hook decision
  // surfaced from claude's hook system. Frontend renders an inline
  // badge so users can see what hooks decided.
  let onHookDecisionCb:
    | ((payload: HookDecisionPayload) => void)
    | undefined;
  // v0.7.68 — extended-thinking content blocks. Claude exposes its
  // reasoning when extended thinking is enabled; the panel renders
  // each as a collapsible disclosure rather than mixing it into
  // the visible assistant prose.
  let onThinkingCb: ((text: string) => void) | undefined;
  // v0.7.69 — interactive permission prompt. Backend pushes when the
  // Agented hook intercepts a PreToolUse; user clicks Approve / Deny
  // in the chat, the answer endpoint unblocks the hook, claude
  // continues.
  let onPermissionRequestCb:
    | ((payload: PermissionRequestPayload) => void)
    | undefined;
  // v0.7.74 — goal-loop SSE events. ``goal_iteration_started``
  // fires before the judge runs, ``goal_iteration_completed``
  // after the verdict lands, ``goal_loop_ended`` when the loop
  // terminates (met / iteration_cap / wall_time_cap / stopped).
  // ``goal_check_disagreement`` is informational — the
  // deterministic check disagrees with the LLM sanity-layer
  // verdict, but the loop continues based on the deterministic
  // verdict.
  let onGoalIterationStartedCb:
    | ((payload: { iteration: number; max_iterations: number }) => void)
    | undefined;
  let onGoalIterationCompletedCb:
    | ((payload: GoalIterationCompletedPayload) => void)
    | undefined;
  let onGoalLoopEndedCb:
    | ((payload: { reason: string; detail: string }) => void)
    | undefined;
  let onGoalCheckDisagreementCb:
    | ((payload: GoalCheckDisagreementPayload) => void)
    | undefined;
  // SP3 — operator intervene note acknowledged by the runner. The panel
  // registers a handler to surface it as a transient toast; loop state is
  // tracked by the ``paused``/``awaitingHuman`` refs above.
  let onIntervenedCb: ((message: string) => void) | undefined;
  // Phase 23 — the stackable policy engine broadcasts ``policy_ask`` when a
  // launch / cost ASK needs an operator decision (same SSE primitive as the
  // human-gate). The panel renders a ``PolicyAskCard`` and POSTs the decision;
  // ``policy_ask_resolved`` clears the card once the wait is settled (by us,
  // another tab, or a fail-closed timeout).
  let onPolicyAskCb: ((payload: PolicyAskEvent) => void) | undefined;
  let onPolicyAskResolvedCb: (() => void) | undefined;

  // SSE lifecycle managed by useEventSource.
  // sourceFactory will be set dynamically via connect() calls.
  // We track the current session ID to build the correct factory at connect time.
  let _streamSessionId: string | null = null;

  const { connect: sseConnect, close: sseClose } = useEventSource({
    // [08.L3] forward give-up options so a terminal disconnect surfaces visibly.
    sourceFactory: (opts) => grdApi.streamSession(projectId.value, _streamSessionId!, opts),
    events: {
      output: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onOutputCb?.(data.line);
        } catch (e) {
          warnParse('[useProjectSession] Failed to parse output event:', e, event.data);
        }
      },
      output_delta: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onOutputDeltaCb?.(data.text ?? '');
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse output_delta event:',
            e,
            event.data,
          );
        }
      },
      ask_user_question: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onAskUserQuestionCb?.({
            tool_use_id: data.tool_use_id ?? '',
            questions: data.questions ?? [],
          });
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse ask_user_question event:',
            e,
            event.data,
          );
        }
      },
      exit_plan_mode: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onExitPlanModeCb?.({
            tool_use_id: data.tool_use_id ?? '',
            plan: data.plan ?? '',
          });
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse exit_plan_mode event:',
            e,
            event.data,
          );
        }
      },
      goal_iteration_started: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onGoalIterationStartedCb?.({
            iteration: data.iteration ?? 0,
            max_iterations: data.max_iterations ?? 0,
          });
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse goal_iteration_started event:',
            e,
            event.data,
          );
        }
      },
      goal_iteration_completed: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onGoalIterationCompletedCb?.({
            iteration: data.iteration ?? 0,
            verdict: data.verdict ?? 'not_met',
            reason: data.reason ?? '',
            source: data.source ?? 'llm',
          });
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse goal_iteration_completed event:',
            e,
            event.data,
          );
        }
      },
      goal_loop_ended: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onGoalLoopEndedCb?.({
            reason: data.reason ?? 'stopped',
            detail: data.detail ?? '',
          });
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse goal_loop_ended event:',
            e,
            event.data,
          );
        }
      },
      goal_check_disagreement: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onGoalCheckDisagreementCb?.({
            iteration: data.iteration ?? 0,
            deterministic_reason: data.deterministic_reason ?? '',
            llm_reason: data.llm_reason ?? '',
            streak: data.streak ?? 0,
          });
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse goal_check_disagreement event:',
            e,
            event.data,
          );
        }
      },
      goal_loop_paused: () => {
        paused.value = true;
      },
      goal_loop_resumed: () => {
        paused.value = false;
      },
      goal_loop_awaiting_human: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          awaitingHuman.value = true;
          gateReason.value = data.gate_reason ?? null;
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse goal_loop_awaiting_human event:',
            e,
            event.data,
          );
        }
      },
      goal_loop_gate_resolved: () => {
        awaitingHuman.value = false;
        gateReason.value = null;
      },
      goal_loop_intervened: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onIntervenedCb?.(data.message ?? '');
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse goal_loop_intervened event:',
            e,
            event.data,
          );
        }
      },
      policy_ask: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onPolicyAskCb?.({
            ask_id: data.ask_id ?? '',
            policy_id: data.policy_id ?? null,
            kind: data.kind ?? null,
            reason: data.reason ?? '',
            scope: data.scope ?? null,
          });
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse policy_ask event:',
            e,
            event.data,
          );
        }
      },
      policy_ask_resolved: () => {
        onPolicyAskResolvedCb?.();
      },
      hook_decision: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onHookDecisionCb?.({
            hook_event: data.hook_event ?? null,
            hook_name: data.hook_name ?? null,
            tool_name: data.tool_name ?? '',
            tool_input: data.tool_input ?? {},
            decision: data.decision,
            outcome: data.outcome ?? null,
          });
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse hook_decision event:',
            e,
            event.data,
          );
        }
      },
      thinking: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onThinkingCb?.(data.text ?? '');
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse thinking event:',
            e,
            event.data,
          );
        }
      },
      permission_request: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          onPermissionRequestCb?.({
            request_id: data.request_id ?? '',
            tool_name: data.tool_name ?? '',
            tool_input: data.tool_input ?? {},
            cwd: data.cwd ?? null,
          });
        } catch (e) {
          warnParse(
            '[useProjectSession] Failed to parse permission_request event:',
            e,
            event.data,
          );
        }
      },
      complete: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          isStreaming.value = false;
          // Update session status in local list
          const idx = sessions.value.findIndex((s) => s.id === _streamSessionId);
          if (idx !== -1) {
            sessions.value[idx] = { ...sessions.value[idx], status: data.status };
          }
          onCompleteCb?.(data.status, data.exit_code, {
            backend: data.backend,
            model: data.model,
          });
          // The subprocess has exited cleanly. The backend has yielded
          // ``complete`` and poisoned its subscriber queue, so the SSE
          // stream is about to close. Close it ourselves first — that
          // suppresses EventSource's auto-reconnect, which would
          // otherwise hit the closed session three times and surface
          // "Connection lost" to the user (the reported bug). The
          // session ended normally, not from a network failure.
          closeStream();
        } catch (e) {
          warnParse('[useProjectSession] Failed to parse complete event:', e, event.data);
        }
      },
      ralph_iteration: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          ralphState.value = {
            iteration: data.iteration ?? 0,
            maxIterations: data.max_iterations ?? 0,
            circuitBreakerTriggered: false,
          };
        } catch (e) {
          warnParse('[useProjectSession] Failed to parse ralph_iteration event:', e, event.data);
        }
      },
      circuit_breaker: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          if (ralphState.value) {
            ralphState.value.circuitBreakerTriggered = true;
          }
          onErrorCb?.(`Circuit breaker: ${data.reason}`);
        } catch (e) {
          warnParse('[useProjectSession] Failed to parse circuit_breaker event:', e, event.data);
        }
      },
      team_update: (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'config') {
            teamState.value = {
              ...(teamState.value || { teamName: null, members: [], tasks: [] }),
              teamName: data.data?.team_name || teamState.value?.teamName || null,
              members: data.data?.members || teamState.value?.members || [],
            };
          } else if (data.type === 'task') {
            if (!teamState.value) {
              teamState.value = { teamName: null, members: [], tasks: [] };
            }
            // Upsert task in array
            const taskIdx = teamState.value.tasks.findIndex(
              (t) => t.id === data.data?.id,
            );
            if (taskIdx >= 0) {
              teamState.value.tasks[taskIdx] = data.data;
            } else if (data.data) {
              teamState.value.tasks.push(data.data);
            }
          }
        } catch (e) {
          warnParse('[useProjectSession] Failed to parse team_update event:', e, event.data);
        }
      },
    },
    onError: () => {
      errorCount++;
      if (errorCount >= 3) {
        closeStream();
        error.value = 'Connection lost';
        onErrorCb?.('Connection lost after 3 retries');
      }
    },
    // [08.L3] Terminal give-up after the max reconnect attempts — surface the
    // same visible "connection lost" state instead of dropping silently.
    onGiveUp: () => {
      closeStream();
      error.value = 'Connection lost';
      onErrorCb?.('Connection lost — reconnection gave up');
    },
  });

  /**
   * Load all sessions for the current project.
   */
  async function loadSessions() {
    try {
      const result = await grdApi.listSessions(projectId.value);
      sessions.value = result.sessions || [];
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to load sessions';
    }
  }

  /**
   * Create a new session and connect to its SSE stream.
   */
  async function startSession(request: CreateSessionRequest) {
    isLoading.value = true;
    error.value = null;
    try {
      const result = await grdApi.createSession(projectId.value, request);
      activeSessionId.value = result.session_id;
      connectStream(result.session_id);
      await loadSessions();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to start session';
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Create a new Ralph loop session and connect to its SSE stream.
   */
  async function startRalphSession(config: RalphConfig) {
    isLoading.value = true;
    error.value = null;
    ralphState.value = {
      iteration: 0,
      maxIterations: config.max_iterations,
      circuitBreakerTriggered: false,
    };
    try {
      const result = await grdApi.createRalphSession(projectId.value, {
        ralph_config: config,
      });
      activeSessionId.value = result.session_id;
      connectStream(result.session_id);
      await loadSessions();
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to start Ralph session';
      ralphState.value = null;
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Create a new Team Spawn session and connect to its SSE stream.
   */
  async function startTeamSession(config: TeamConfig) {
    isLoading.value = true;
    error.value = null;
    teamState.value = { teamName: null, members: [], tasks: [] };
    try {
      const result = await grdApi.createTeamSession(projectId.value, {
        team_config: config,
      });
      activeSessionId.value = result.session_id;
      teamState.value = {
        teamName: result.team_name,
        members: [],
        tasks: [],
      };
      connectStream(result.session_id);
      await loadSessions();
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to start team session';
      teamState.value = null;
    } finally {
      isLoading.value = false;
    }
  }

  /**
   * Connect to the SSE stream for a session.
   * Always closes any existing stream first to prevent connection leaks.
   */
  function connectStream(sessionId: string) {
    closeStream();
    isStreaming.value = true;
    errorCount = 0;
    _streamSessionId = sessionId;
    sseConnect();
  }

  /**
   * Send text input to the active session's PTY stdin.
   *
   * v0.7.70 — ``attachments`` is an optional bag of per-prompt
   * context bits (files, snippets, URLs, entity refs). When
   * present, the backend compiles them through
   * ``ContextCompilerService`` and prepends a rendered
   * ``=== Operator Context ===`` block to ``text`` before
   * forwarding to the CLI. Pass ``undefined`` (or omit) for the
   * legacy "no extra context" behavior — payload + bytes on the
   * wire are identical to pre-v0.7.70.
   */
  async function sendInput(
    text: string,
    attachments?: Array<Record<string, unknown>>,
  ) {
    if (!activeSessionId.value) return;
    try {
      await grdApi.sendInput(
        projectId.value,
        activeSessionId.value,
        text,
        attachments,
      );
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to send input';
    }
  }

  /**
   * Stop the active session.
   */
  async function stopSession() {
    if (!activeSessionId.value) return;
    try {
      await grdApi.stopSession(projectId.value, activeSessionId.value);
      closeStream();
      await loadSessions();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to stop session';
    }
  }

  /**
   * Pause the active session.
   */
  async function pauseSession() {
    if (!activeSessionId.value) return;
    try {
      await grdApi.pauseSession(projectId.value, activeSessionId.value);
      await loadSessions();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to pause session';
    }
  }

  /**
   * Resume the active session and re-establish SSE connection.
   */
  async function resumeSession() {
    if (!activeSessionId.value) return;
    try {
      await grdApi.resumeSession(projectId.value, activeSessionId.value);
      connectStream(activeSessionId.value);
      await loadSessions();
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to resume session';
    }
  }

  /**
   * Switch to a different session. Closes existing stream and reconnects
   * if the target session is active or paused.
   */
  function switchSession(sessionId: string) {
    activeSessionId.value = sessionId;
    closeStream();
    ralphState.value = null;
    teamState.value = null;
    const session = sessions.value.find((s) => s.id === sessionId);
    if (session && (session.status === 'active' || session.status === 'paused')) {
      connectStream(sessionId);
    }
  }

  /**
   * Close the current SSE connection.
   */
  function closeStream() {
    sseClose();
    isStreaming.value = false;
    ralphState.value = null;
    teamState.value = null;
    paused.value = false;
    awaitingHuman.value = false;
    gateReason.value = null;
  }

  // Callback setters
  function onOutput(cb: (line: string) => void) {
    onOutputCb = cb;
  }

  function onOutputDelta(cb: (delta: string) => void) {
    onOutputDeltaCb = cb;
  }

  function onComplete(
    cb: (status: string, exitCode: number, meta?: { backend?: string; model?: string }) => void,
  ) {
    onCompleteCb = cb;
  }

  function onError(cb: (message: string) => void) {
    onErrorCb = cb;
  }

  function onAskUserQuestion(
    cb: (payload: { tool_use_id: string; questions: AskUserQuestionItem[] }) => void,
  ) {
    onAskUserQuestionCb = cb;
  }

  function onExitPlanMode(
    cb: (payload: { tool_use_id: string; plan: string }) => void,
  ) {
    onExitPlanModeCb = cb;
  }

  function onHookDecision(cb: (payload: HookDecisionPayload) => void) {
    onHookDecisionCb = cb;
  }

  function onThinking(cb: (text: string) => void) {
    onThinkingCb = cb;
  }

  function onPermissionRequest(
    cb: (payload: PermissionRequestPayload) => void,
  ) {
    onPermissionRequestCb = cb;
  }

  // v0.7.74 — goal-loop event handler registration.
  function onGoalIterationStarted(
    cb: (payload: { iteration: number; max_iterations: number }) => void,
  ) {
    onGoalIterationStartedCb = cb;
  }

  function onGoalIterationCompleted(
    cb: (payload: GoalIterationCompletedPayload) => void,
  ) {
    onGoalIterationCompletedCb = cb;
  }

  function onGoalLoopEnded(
    cb: (payload: { reason: string; detail: string }) => void,
  ) {
    onGoalLoopEndedCb = cb;
  }

  function onGoalCheckDisagreement(
    cb: (payload: GoalCheckDisagreementPayload) => void,
  ) {
    onGoalCheckDisagreementCb = cb;
  }

  // SP3 — operator intervene acknowledgement handler registration.
  function onIntervened(cb: (message: string) => void) {
    onIntervenedCb = cb;
  }

  // Phase 23 — policy ASK card handler registration.
  function onPolicyAsk(cb: (payload: PolicyAskEvent) => void) {
    onPolicyAskCb = cb;
  }

  function onPolicyAskResolved(cb: () => void) {
    onPolicyAskResolvedCb = cb;
  }

  // SSE connection cleanup is handled by useEventSource's onUnmounted.
  // This separate onUnmounted resets streaming/ralph/team state on unmount.
  onUnmounted(() => {
    isStreaming.value = false;
    ralphState.value = null;
    teamState.value = null;
  });

  return {
    // State
    sessions,
    activeSessionId,
    isStreaming,
    isLoading,
    error,
    ralphState,
    teamState,
    paused,
    awaitingHuman,
    gateReason,
    // Methods
    loadSessions,
    startSession,
    startRalphSession,
    startTeamSession,
    connectStream,
    sendInput,
    stopSession,
    pauseSession,
    resumeSession,
    switchSession,
    closeStream,
    // Callback setters
    onOutput,
    onOutputDelta,
    onComplete,
    onError,
    onAskUserQuestion,
    onExitPlanMode,
    onHookDecision,
    onThinking,
    onPermissionRequest,
    onGoalIterationStarted,
    onGoalIterationCompleted,
    onGoalLoopEnded,
    onGoalCheckDisagreement,
    onIntervened,
    onPolicyAsk,
    onPolicyAskResolved,
  };
}
