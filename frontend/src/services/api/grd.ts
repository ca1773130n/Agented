/**
 * GRD project management API module.
 *
 * Provides typed methods for syncing GRD .planning/ data, listing milestones,
 * phases, plans, and updating plan status.
 */
import { apiFetch, createAuthenticatedEventSource } from './client';
import type { AuthenticatedEventSource } from './client';

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
  execution_type: 'direct' | 'ralph_loop' | 'team_spawn';
  execution_mode: 'autonomous' | 'interactive';
  idle_timeout_seconds: number;
  max_lifetime_seconds: number;
  last_activity_at: string | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface CreateSessionRequest {
  cmd: string[];
  cwd?: string;
  phase_id?: string;
  plan_id?: string;
  agent_id?: string;
  worktree_path?: string;
  execution_type?: 'direct' | 'ralph_loop' | 'team_spawn';
  execution_mode?: 'autonomous' | 'interactive';
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

  sendInput: (projectId: string, sessionId: string, text: string) =>
    apiFetch<{ message: string; session_id: string }>(
      `/api/projects/${projectId}/sessions/${sessionId}/input`,
      { method: 'POST', body: JSON.stringify({ text }) }
    ),

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
  streamSession: (projectId: string, sessionId: string): AuthenticatedEventSource =>
    createAuthenticatedEventSource(`/api/projects/${projectId}/sessions/${sessionId}/stream`),

  // Project AI Chat
  sendProjectChat: (
    projectId: string,
    data: { content: string; milestone_id?: string },
  ) =>
    apiFetch<{ status: string; session_id: string; super_agent_id: string }>(
      `/api/projects/${projectId}/chat`,
      { method: 'POST', body: JSON.stringify(data) },
    ),

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
};
