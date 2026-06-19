/**
 * GRD project management API module.
 *
 * Provides typed methods for syncing GRD .planning/ data, listing milestones,
 * phases, plans, and updating plan status.
 */
import { apiFetch, createAuthenticatedEventSource } from './client';
import type { AuthenticatedEventSource, AuthenticatedEventSourceOptions } from './client';

export interface GrdMilestone {
  id: string;
  project_id: string;
  version: string;
  title: string;
  description: string | null;
  status: 'planning' | 'active' | 'completed' | 'archived';
  created_at: string | null;
  updated_at: string | null;
}

export interface GrdPhase {
  id: string;
  milestone_id: string;
  phase_number: number;
  name: string;
  status: 'pending' | 'active' | 'completed' | 'skipped';
  verification_level: string;
  goal: string | null;
  wave: number | null;
  plan_count: number;
}

export interface GrdPlan {
  id: string;
  phase_id: string;
  plan_number: number;
  title: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'in_review';
  verification_level: string;
  wave: number | null;
  autonomous: boolean | null;
  files_modified: string[] | null;
}

export interface GrdSyncResult {
  synced: number;
  skipped: number;
  errors: string[];
}

export interface GrdSyncStatus {
  last_synced_at: string | null;
  file_count: number;
  grd_available: boolean;
}

export interface GrdSession {
  id: string;
  project_id: string;
  phase_id: string | null;
  plan_id: string | null;
  agent_id: string | null;
  status: 'active' | 'paused' | 'completed' | 'failed';
  pid: number | null;
  pgid: number | null;
  worktree_path: string | null;
  execution_type: 'direct' | 'ralph_loop' | 'team_spawn' | 'goal_loop';
  execution_mode: 'autonomous' | 'interactive';
  idle_timeout_seconds: number;
  max_lifetime_seconds: number;
  last_activity_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  // v0.7.57 — session-start dialog fields persisted on the row.
  name?: string | null;
  auto_title?: boolean;
  yolo_mode?: boolean;
}

export interface CreateSessionRequest {
  cmd: string[];
  cwd?: string;
  phase_id?: string;
  plan_id?: string;
  agent_id?: string;
  worktree_path?: string;
  execution_type?: 'direct' | 'ralph_loop' | 'team_spawn' | 'goal_loop';
  execution_mode?: 'autonomous' | 'interactive';
  // When true, the backend parses claude's ``--output-format stream-json``
  // events and the input endpoint wraps user text in the SDK envelope
  // claude expects with ``--input-format stream-json``. The cmd must
  // already include those flags; this flag just tells the backend to
  // switch its parsers/wrappers to match.
  stream_json?: boolean;
  // When false, the backend spawns the child via ``subprocess.Popen``
  // with stdin/stdout pipes instead of ``pty.fork()``. Required for
  // ``claude --print`` (it refuses to read from a tty). Defaults true
  // on the server so ralph loops and team-spawn keep their PTY.
  use_pty?: boolean;
  // v0.7.57 — session-start dialog fields. ``name`` is the user-
  // supplied title; ``auto_title=true`` tells the backend to fill it
  // in (today: simple fallback; later: claude-summary). ``yolo_mode``
  // appends ``--dangerously-skip-permissions`` and (v0.7.58) bypasses
  // the per-project account whitelist.
  name?: string | null;
  auto_title?: boolean;
  yolo_mode?: boolean;
  // v0.7.58 — required when yolo_mode is false; backend enforces it
  // is in the project's allowed-accounts whitelist.
  account_id?: string;
  // v0.7.70 — optional Forge context wiring. ``session_overrides``
  // lets the dialog opt out of project bindings or add session-only
  // bindings. ``attachments`` here are the FIRST prompt's
  // attachments (rarely used at session-create time; usually they
  // arrive via ``sendInput``).
  forge_context?: {
    session_overrides?: {
      disabled_binding_ids?: number[];
      additions?: Array<{
        kind: 'rule' | 'skill' | 'hook' | 'command' | 'mcp_server' | 'plugin';
        asset_id: string;
        role?: string | null;
      }>;
    };
    attachments?: Array<Record<string, unknown>>;
  };
  // v0.7.74 — goal-loop config. Only consumed by the ``goal_loop``
  // execution-type handler; other types ignore it. Empty when not
  // creating a goal-loop session.
  goal_loop_config?: GoalLoopConfig;
}

// v0.7.74 / v0.6.0 — goal-loop config consumed by the ``goal_loop``
// execution-type handler. The v0.6.0 unified-loops fields
// (``max_tokens`` / ``context_policy`` / ``stagnation_no_progress_for``)
// map onto the typed ``LoopSpec`` exit/state in the backend.
export interface GoalLoopConfig {
  goal: string;
  check_cmd?: string | null;
  max_iterations?: number;
  max_wall_seconds?: number;
  max_cost_usd?: number;
  ouroboros?: boolean;
  judge_backend_kind?: 'claude' | 'codex' | 'gemini' | 'opencode';
  judge_model_override?: string | null;
  metric_spec?: Record<string, unknown> | null;
  // v0.6.0 unified loops
  max_tokens?: number;
  context_policy?: 'carry' | 'reset';
  stagnation_no_progress_for?: number;
}

// v0.7.74 — goal-loop iteration audit row + container response.
export interface GoalLoopIteration {
  id: number;
  session_id: string;
  iteration: number;
  started_at: string;
  ended_at: string | null;
  verdict: 'met' | 'not_met' | null;
  // ``'stopped'`` is written when the operator stops the session
  // while the judge is mid-run (v0.7.74 codex fix #4). The row is
  // finalized but the verdict was never broadcast to subscribers.
  judge_source:
    | 'pending'
    | 'deterministic'
    | 'llm'
    | 'cap'
    | 'stopped';
  judge_reason: string | null;
  judge_stdout: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
}

export interface GoalLoopAudit {
  session_id: string;
  config: {
    goal: string;
    check_cmd?: string | null;
    max_iterations: number;
    max_wall_seconds: number;
    judge_backend_kind: string;
    judge_model_override?: string | null;
  } | null;
  iterations: GoalLoopIteration[];
}

export interface CreateSessionResponse {
  session_id: string;
  pid: number;
  status: string;
}

export interface SessionOutputResponse {
  lines: string[];
  count: number;
}

export interface PersistedSessionMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  ts: string;
}

export interface SessionMessagesResponse {
  messages: PersistedSessionMessage[];
  count: number;
}

export interface RalphConfig {
  max_iterations: number;
  completion_promise: string;
  task_description: string;
  no_progress_threshold: number;
}

export interface TeamConfig {
  team_size: number;
  task_description: string;
  roles: string[];
}

export interface CreateRalphSessionRequest {
  cwd?: string;
  phase_id?: string;
  plan_id?: string;
  agent_id?: string;
  ralph_config: RalphConfig;
}

export interface CreateTeamSessionRequest {
  cwd?: string;
  phase_id?: string;
  plan_id?: string;
  agent_id?: string;
  team_config: TeamConfig;
}

export interface SessionMonitorData {
  alive: boolean;
  status: string;
  output_lines: number;
  last_activity_at: string | null;
  // Ralph-specific
  iteration?: number;
  max_iterations?: number;
  circuit_breaker_triggered?: boolean;
  // Team-specific
  team_name?: string;
  team_members?: Array<{ name: string; agentId: string; agentType: string }>;
  tasks?: Array<{ id: string; subject: string; status: string; owner?: string }>;
}

// v0.8.0 — one-click team harness setup step row (REQ-19 / SC1).
export interface GrdHarnessSetupStep {
  step_key: string;
  status: string; // 'pending' | 'ok' | 'skipped' | 'failed'
  detail?: string | null;
  fingerprint?: string | null;
}

export const grdApi = {
  getSyncStatus: (projectId: string) =>
    apiFetch<GrdSyncStatus>(`/api/projects/${projectId}/sync`),

  sync: (projectId: string) =>
    apiFetch<GrdSyncResult>(`/api/projects/${projectId}/sync`, { method: 'POST' }),

  listMilestones: (projectId: string) =>
    apiFetch<{ milestones: GrdMilestone[] }>(`/api/projects/${projectId}/milestones`),

  listPhases: (projectId: string, milestoneId?: string) => {
    const qs = milestoneId ? `?milestone_id=${milestoneId}` : '';
    return apiFetch<{ phases: GrdPhase[] }>(`/api/projects/${projectId}/phases${qs}`);
  },

  createPhase: (
    projectId: string,
    data: { milestone_id: string; name: string; goal?: string; status?: string },
  ) =>
    apiFetch<{ message: string; phase: GrdPhase }>(`/api/projects/${projectId}/phases`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listPlans: (projectId: string, phaseId?: string) => {
    const qs = phaseId ? `?phase_id=${phaseId}` : '';
    return apiFetch<{ plans: GrdPlan[] }>(`/api/projects/${projectId}/plans${qs}`);
  },

  updatePlanStatus: (projectId: string, planId: string, status: string) =>
    apiFetch<{ message: string; plan: GrdPlan }>(
      `/api/projects/${projectId}/plans/${planId}/status`,
      {
        method: 'PUT',
        body: JSON.stringify({ status }),
      }
    ),

  createPlan: (
    projectId: string,
    data: { phase_id: string; title: string; description?: string; status?: string; tasks_json?: string },
  ) =>
    apiFetch<{ message: string; plan: GrdPlan }>(`/api/projects/${projectId}/plans`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updatePlan: (
    projectId: string,
    planId: string,
    data: { title?: string; description?: string; status?: string; tasks_json?: string },
  ) =>
    apiFetch<{ message: string; plan: GrdPlan }>(`/api/projects/${projectId}/plans/${planId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deletePlan: (projectId: string, planId: string) =>
    apiFetch<{ message: string }>(`/api/projects/${projectId}/plans/${planId}`, {
      method: 'DELETE',
    }),

  // Session management
  createSession: (projectId: string, request: CreateSessionRequest) =>
    apiFetch<CreateSessionResponse>(`/api/projects/${projectId}/sessions`, {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  listSessions: (projectId: string) =>
    apiFetch<{ sessions: GrdSession[] }>(`/api/projects/${projectId}/sessions`),

  getSessionOutput: (projectId: string, sessionId: string, lastN = 100) =>
    apiFetch<SessionOutputResponse>(
      `/api/projects/${projectId}/sessions/${sessionId}/output?last_n=${lastN}`
    ),

  // Persisted chat history. Sourced from ``project_sessions.log_json``
  // — survives subprocess exit and gunicorn restart, unlike the
  // in-memory ring buffer that ``getSessionOutput`` reads. Backend-
  // agnostic: the same flow works for claude / codex / gemini /
  // opencode since we log on the user-input and assistant-output
  // sides of the SSE pipeline, before the bytes reach a specific
  // CLI's transcript format.
  getSessionMessages: (projectId: string, sessionId: string) =>
    apiFetch<SessionMessagesResponse>(
      `/api/projects/${projectId}/sessions/${sessionId}/messages`
    ),

  // v0.7.63 — answer an ``AskUserQuestion`` tool_use. ``answers`` maps
  // each question's text to the selected option's label (or array of
  // labels for multi-select). Backend wraps in a tool_result envelope
  // and writes to claude's stdin.
  answerSessionQuestion: (
    projectId: string,
    sessionId: string,
    toolUseId: string,
    answers: Record<string, string | string[]>,
  ) =>
    apiFetch<{ message: string; session_id: string }>(
      `/api/projects/${projectId}/sessions/${sessionId}/answer-question`,
      {
        method: 'POST',
        body: JSON.stringify({ tool_use_id: toolUseId, answers }),
      },
    ),

  // v0.7.65 — answer claude's ``ExitPlanMode`` tool_use. ``approved``
  // is a boolean: true → "proceed with execution", false → "keep
  // planning". Backend translates to claude's expected tool_result
  // contract.
  answerSessionPlan: (
    projectId: string,
    sessionId: string,
    toolUseId: string,
    approved: boolean,
  ) =>
    apiFetch<{ message: string; session_id: string }>(
      `/api/projects/${projectId}/sessions/${sessionId}/answer-plan`,
      {
        method: 'POST',
        body: JSON.stringify({ tool_use_id: toolUseId, approved }),
      },
    ),

  // v0.7.69 — user's decision on an Agented permission prompt. The
  // backend resolves the pending request, the parked hook script
  // unblocks, and claude proceeds (or skips) based on the decision.
  answerPermissionPrompt: (
    projectId: string,
    sessionId: string,
    requestId: string,
    decision: 'allow' | 'deny',
  ) =>
    apiFetch<{
      request_id: string;
      decision: string;
      resolved: boolean;
    }>(
      `/api/projects/${projectId}/sessions/${sessionId}/permission-decision`,
      {
        method: 'POST',
        body: JSON.stringify({ request_id: requestId, decision }),
      },
    ),

  // v0.7.58 — per-project AI backend account whitelist.
  // Sessions started without yolo_mode require an account_id from
  // this list. Managed on the project settings page.
  listAllowedAccounts: (projectId: string) =>
    apiFetch<{ allowed_accounts: { account_id: string; created_at: string }[] }>(
      `/api/projects/${projectId}/allowed-accounts`,
    ),

  addAllowedAccount: (projectId: string, accountId: string) =>
    apiFetch<{ project_id: string; account_id: string; inserted: boolean }>(
      `/api/projects/${projectId}/allowed-accounts`,
      {
        method: 'POST',
        body: JSON.stringify({ account_id: accountId }),
      },
    ),

  removeAllowedAccount: (projectId: string, accountId: string) =>
    apiFetch<{ project_id: string; account_id: string; removed: boolean }>(
      `/api/projects/${projectId}/allowed-accounts/${accountId}`,
      { method: 'DELETE' },
    ),

  stopSession: (projectId: string, sessionId: string) =>
    apiFetch<{ message: string; session_id: string }>(
      `/api/projects/${projectId}/sessions/${sessionId}/stop`,
      { method: 'POST' }
    ),

  pauseSession: (projectId: string, sessionId: string) =>
    apiFetch<{ message: string; session_id: string }>(
      `/api/projects/${projectId}/sessions/${sessionId}/pause`,
      { method: 'POST' }
    ),

  resumeSession: (projectId: string, sessionId: string) =>
    apiFetch<{ message: string; session_id: string }>(
      `/api/projects/${projectId}/sessions/${sessionId}/resume`,
      { method: 'POST' }
    ),

  sendInput: (
    projectId: string,
    sessionId: string,
    text: string,
    attachments?: Array<Record<string, unknown>>,
  ) => {
    // v0.7.70 — per-prompt attachments. Backend compiles a context
    // bundle from the attachments + project bindings and prepends
    // the rendered ``Operator Context`` block to ``text`` before
    // forwarding to the CLI.
    const payload: Record<string, unknown> = { text };
    if (attachments && attachments.length > 0) {
      payload.attachments = attachments;
    }
    return apiFetch<{ message: string; session_id: string }>(
      `/api/projects/${projectId}/sessions/${sessionId}/input`,
      { method: 'POST', body: JSON.stringify(payload) },
    );
  },

  // Ralph/Team session creation
  createRalphSession: (projectId: string, request: CreateRalphSessionRequest) =>
    apiFetch<{ session_id: string; pid: number; status: string }>(
      `/api/projects/${projectId}/sessions/ralph`,
      { method: 'POST', body: JSON.stringify(request) }
    ),

  createTeamSession: (projectId: string, request: CreateTeamSessionRequest) =>
    apiFetch<{ session_id: string; pid: number; status: string; team_name: string }>(
      `/api/projects/${projectId}/sessions/team`,
      { method: 'POST', body: JSON.stringify(request) }
    ),

  // v0.7.74 — iteration audit for goal_loop sessions.
  listGoalIterations: (projectId: string, sessionId: string) =>
    apiFetch<GoalLoopAudit>(
      `/api/projects/${projectId}/sessions/${sessionId}/goal-iterations`,
    ),

  getSessionMonitor: (projectId: string, sessionId: string) =>
    apiFetch<SessionMonitorData>(
      `/api/projects/${projectId}/sessions/${sessionId}/monitor`
    ),

  /**
   * SSE stream helper -- returns EventSource directly (NOT a Promise).
   * Unlike other grdApi methods that return Promise<T> via apiFetch,
   * this returns an EventSource instance. Caller manages lifecycle
   * by attaching onmessage/onerror handlers and calling .close().
   */
  // [08.L3] `options` is forwarded so callers can wire onGiveUp / onQueueOverflow
  // and surface a visible "connection lost" state instead of a silent give-up.
  streamSession: (
    projectId: string,
    sessionId: string,
    options?: AuthenticatedEventSourceOptions,
  ): AuthenticatedEventSource =>
    createAuthenticatedEventSource(`/api/projects/${projectId}/sessions/${sessionId}/stream`, options),

  // Project AI Chat
  sendProjectChat: (
    projectId: string,
    data: { content: string; milestone_id?: string; useCliAgent?: boolean },
  ) => {
    const { useCliAgent, ...rest } = data;
    const payload: Record<string, unknown> = { ...rest };
    if (typeof useCliAgent === 'boolean') {
      payload.use_cli_agent = useCliAgent;
    }
    return apiFetch<{ status: string; session_id: string; super_agent_id: string }>(
      `/api/projects/${projectId}/chat`,
      { method: 'POST', body: JSON.stringify(payload) },
    );
  },

  streamProjectChat: (projectId: string): AuthenticatedEventSource =>
    createAuthenticatedEventSource(`/api/projects/${projectId}/chat/stream`),

  // Planning command invocation
  invokePlanningCommand: (
    projectId: string,
    command: string,
    args?: Record<string, string>,
  ) =>
    apiFetch<{ session_id: string; status: string }>(
      `/api/projects/${projectId}/planning/invoke`,
      {
        method: 'POST',
        body: JSON.stringify({ command, args }),
      },
    ),

  // Planning initialization status
  getPlanningStatus: (projectId: string) =>
    apiFetch<{ grd_init_status: string; active_session_id: string | null }>(
      `/api/projects/${projectId}/planning/status`,
    ),

  // v0.8.0 — one-click team harness setup (REQ-19 / SC1).
  // Trigger flips status → 'running' and runs the six-step setup off-thread.
  triggerHarnessSetup: (projectId: string) =>
    apiFetch<{ harness_setup_status: string }>(
      `/api/projects/${projectId}/harness-setup`,
      { method: 'POST' },
    ),

  getHarnessSetupStatus: (projectId: string) =>
    apiFetch<{ harness_setup_status: string; steps: GrdHarnessSetupStep[] }>(
      `/api/projects/${projectId}/harness-setup/status`,
    ),

  // SSE stream of step progress. Returns an EventSource directly (NOT a
  // Promise); caller manages lifecycle and listens for 'step'/'done' events.
  streamHarnessSetup: (projectId: string): AuthenticatedEventSource =>
    createAuthenticatedEventSource(`/api/projects/${projectId}/harness-setup/stream`),
};
