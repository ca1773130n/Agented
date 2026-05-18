/**
 * SuperAgent, Document, Session, and Message API modules.
 */
import { API_BASE, apiFetch, createAuthenticatedEventSource } from './client';
import type { AuthenticatedEventSource } from './client';
import type {
  SuperAgent,
  SuperAgentDocument,
  SuperAgentSession,
  AgentMessage,
  DocumentType,
  AgentMessageType,
  AgentMessagePriority,
  GitActionRequest,
  GitActionResponse,
  SessionType,
} from './types';

export interface SuperAgentActivityStatus {
  active_sessions: number;
  is_streaming: boolean;
}

export const superAgentApi = {
  list: () => apiFetch<{ super_agents: SuperAgent[] }>('/admin/super-agents'),
  /** Per-SA activity snapshot keyed by super_agent_id. SAs with no
   *  active sessions are absent from the map (callers should treat
   *  ``undefined`` as "idle"). Cheap enough to poll on a 5-10s
   *  cadence; powers the activity pill on the SA list page. */
  activityStatus: () =>
    apiFetch<{ statuses: Record<string, SuperAgentActivityStatus> }>(
      '/admin/super-agents/activity-status',
    ),
  get: (id: string) => apiFetch<SuperAgent>(`/admin/super-agents/${id}`),
  create: (data: { name: string; description?: string; backend_type?: string; preferred_model?: string; team_id?: string; max_concurrent_sessions?: number; config_json?: string }) =>
    apiFetch<{ message: string; super_agent_id: string }>('/admin/super-agents', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<Omit<SuperAgent, 'id' | 'created_at' | 'updated_at'>>) =>
    apiFetch<{ message: string }>(`/admin/super-agents/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    apiFetch<{ message: string }>(`/admin/super-agents/${id}`, { method: 'DELETE' }),
  // v0.7.92 — Ouroboros bridge (PR #138 backend + this PR frontend).
  // Spawns a goal_loop project session that inherits the SA's
  // backend/model and runs in Ouroboros mode (hypothesis → verdict
  // → dead-end → convergence). The returned session_id can be
  // streamed via the standard project-session SSE endpoint.
  startOuroborosRun: (
    id: string,
    body: {
      project_id?: string;
      goal: string;
      max_iterations?: number;
      max_wall_seconds?: number;
      check_cmd?: string | null;
      yolo_mode?: boolean;
    },
  ) =>
    apiFetch<{
      session_id: string;
      project_id: string;
      super_agent_id: string;
      status: string;
      system_prompt_applied: boolean;
      pid?: number;
    }>(`/admin/super-agents/${id}/ouroboros-runs`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  listOuroborosRuns: (id: string, limit = 20) =>
    apiFetch<{
      runs: Array<{
        session_id: string;
        project_id: string;
        status: string;
        execution_type: string;
        started_at: string | null;
        ended_at: string | null;
        last_activity_at: string | null;
        iteration_count: number;
      }>;
    }>(`/admin/super-agents/${id}/ouroboros-runs?limit=${limit}`),
};

export const superAgentDocumentApi = {
  list: (superAgentId: string) =>
    apiFetch<{ documents: SuperAgentDocument[] }>(`/admin/super-agents/${superAgentId}/documents`),
  get: (superAgentId: string, docId: number) =>
    apiFetch<SuperAgentDocument>(`/admin/super-agents/${superAgentId}/documents/${docId}`),
  create: (superAgentId: string, data: { doc_type: DocumentType; title: string; content?: string }) =>
    apiFetch<{ message: string; document_id: number }>(`/admin/super-agents/${superAgentId}/documents`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (superAgentId: string, docId: number, data: { title?: string; content?: string }) =>
    apiFetch<{ message: string }>(`/admin/super-agents/${superAgentId}/documents/${docId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (superAgentId: string, docId: number) =>
    apiFetch<{ message: string }>(`/admin/super-agents/${superAgentId}/documents/${docId}`, { method: 'DELETE' }),
};

export const superAgentSessionApi = {
  list: (superAgentId: string) =>
    apiFetch<{ sessions: SuperAgentSession[] }>(`/admin/super-agents/${superAgentId}/sessions`),
  get: (superAgentId: string, sessionId: string) =>
    apiFetch<SuperAgentSession>(`/admin/super-agents/${superAgentId}/sessions/${sessionId}`),
  create: (superAgentId: string, data?: { project_id?: string; title?: string; session_type?: SessionType }) =>
    apiFetch<{ message: string; session_id: string; worktree_path?: string; branch_name?: string; session_type?: SessionType }>(
      `/admin/super-agents/${superAgentId}/sessions`,
      { method: 'POST', body: data ? JSON.stringify(data) : undefined },
    ),
  /** Legacy stream endpoint (session-level events). */
  stream: (superAgentId: string, sessionId: string): AuthenticatedEventSource =>
    createAuthenticatedEventSource(`${API_BASE}/admin/super-agents/${superAgentId}/sessions/${sessionId}/stream`),
  /** Chat-specific SSE stream for state_delta events (37-02 protocol). */
  chatStream: (superAgentId: string, sessionId: string): AuthenticatedEventSource =>
    createAuthenticatedEventSource(`${API_BASE}/admin/super-agents/${superAgentId}/sessions/${sessionId}/chat/stream`),
  /** Legacy send message endpoint. */
  sendMessage: (superAgentId: string, sessionId: string, message: string) =>
    apiFetch<{ message: string }>(`/admin/super-agents/${superAgentId}/sessions/${sessionId}/message`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  /** Chat endpoint with backend/account/model selection (37-02 protocol).
   *
   * `useCliAgent` overrides the global YOLO setting for this turn only —
   * the AiChatPanel `useCliRunner` toggle plumbs through here. `true`
   * forces the CLI agent runner (tool-using); `false` forces CLIProxy;
   * `undefined` defers to the server's global `agent_yolo_mode`. */
  sendChatMessage: (
    superAgentId: string,
    sessionId: string,
    content: string,
    options?: {
      backend?: string;
      account_id?: string;
      model?: string;
      mode?: string;
      chat_mode?: string;
      useCliAgent?: boolean;
    },
  ) => {
    const { useCliAgent, ...rest } = options ?? {};
    const payload: Record<string, unknown> = { content, ...rest };
    if (typeof useCliAgent === 'boolean') {
      payload.use_cli_agent = useCliAgent;
    }
    return apiFetch<{ status: string; message_id: string; backends?: Record<string, unknown> }>(
      `/admin/super-agents/${superAgentId}/sessions/${sessionId}/chat`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    );
  },
  end: (superAgentId: string, sessionId: string) =>
    apiFetch<{ message: string }>(`/admin/super-agents/${superAgentId}/sessions/${sessionId}/end`, {
      method: 'POST',
    }),
  gitAction: (superAgentId: string, sessionId: string, data: GitActionRequest) =>
    apiFetch<GitActionResponse>(`/admin/super-agents/${superAgentId}/sessions/${sessionId}/git-action`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

export const agentMessageApi = {
  listInbox: (agentId: string) =>
    apiFetch<{ messages: AgentMessage[] }>(`/admin/super-agents/${agentId}/messages/inbox`),
  listOutbox: (agentId: string) =>
    apiFetch<{ messages: AgentMessage[] }>(`/admin/super-agents/${agentId}/messages/outbox`),
  send: (agentId: string, data: { to_agent_id?: string; message_type?: AgentMessageType; priority?: AgentMessagePriority; subject?: string; content: string; ttl_seconds?: number }) =>
    apiFetch<{ message: string; message_id: string }>(`/admin/super-agents/${agentId}/messages`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  markRead: (agentId: string, messageId: string) =>
    apiFetch<{ message: string }>(`/admin/super-agents/${agentId}/messages/${messageId}/read`, {
      method: 'POST',
    }),
  delete: (agentId: string, messageId: string) =>
    apiFetch<{ message: string }>(`/admin/super-agents/${agentId}/messages/${messageId}`, {
      method: 'DELETE',
    }),
};
