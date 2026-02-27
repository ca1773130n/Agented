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
} from './types';

export const superAgentApi = {
  list: () => apiFetch<{ super_agents: SuperAgent[] }>('/admin/super-agents'),
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
  create: (superAgentId: string) =>
    apiFetch<{ message: string; session_id: string }>(`/admin/super-agents/${superAgentId}/sessions`, {
      method: 'POST',
    }),
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
  /** Chat endpoint with backend/account/model selection (37-02 protocol). */
  sendChatMessage: (
    superAgentId: string,
    sessionId: string,
    content: string,
    options?: { backend?: string; account_id?: string; model?: string; mode?: string },
  ) =>
    apiFetch<{ status: string; message_id: string; backends?: Record<string, unknown> }>(
      `/admin/super-agents/${superAgentId}/sessions/${sessionId}/chat`,
      {
        method: 'POST',
        body: JSON.stringify({ content, ...options }),
      },
    ),
  end: (superAgentId: string, sessionId: string) =>
    apiFetch<{ message: string }>(`/admin/super-agents/${superAgentId}/sessions/${sessionId}/end`, {
      method: 'POST',
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
