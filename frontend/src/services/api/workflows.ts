/**
 * Workflow and workflow execution API modules.
 */
import { API_BASE, apiFetch, createAuthenticatedEventSource } from './client';
import type { AuthenticatedEventSource, AuthenticatedEventSourceOptions } from './client';
import type {
  Workflow,
  WorkflowVersion,
  WorkflowExecution,
  WorkflowNodeExecution,
  ConversationMessage,
} from './types';

export const workflowApi = {
  list: () => apiFetch<{ workflows: Workflow[] }>('/admin/workflows'),
  get: (id: string) => apiFetch<Workflow>(`/admin/workflows/${id}`),
  create: (data: { name: string; description?: string; trigger_type?: string; trigger_config?: string }) =>
    apiFetch<{ message: string; workflow_id: string }>('/admin/workflows', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<Omit<Workflow, 'id' | 'created_at' | 'updated_at'>>) =>
    apiFetch<{ message: string }>(`/admin/workflows/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    apiFetch<{ message: string }>(`/admin/workflows/${id}`, { method: 'DELETE' }),
  // Version management
  listVersions: (workflowId: string) =>
    apiFetch<{ versions: WorkflowVersion[] }>(`/admin/workflows/${workflowId}/versions`),
  createVersion: (workflowId: string, data: { graph_json: string }) =>
    apiFetch<{ message: string; version: number }>(`/admin/workflows/${workflowId}/versions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getVersion: (workflowId: string, version: number) =>
    apiFetch<WorkflowVersion>(`/admin/workflows/${workflowId}/versions/${version}`),
};

export const workflowExecutionApi = {
  list: (workflowId: string) =>
    apiFetch<{ executions: WorkflowExecution[] }>(`/admin/workflows/${workflowId}/executions`),
  get: (_workflowId: string, executionId: string) =>
    apiFetch<{ execution: WorkflowExecution; node_executions: WorkflowNodeExecution[] }>(
      `/admin/workflows/executions/${executionId}`
    ),
  run: (workflowId: string, data?: { input_json?: string }) =>
    apiFetch<{ message: string; execution_id: string }>(`/admin/workflows/${workflowId}/run`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),
  cancel: (workflowId: string, executionId: string) =>
    apiFetch<{ message: string }>(`/admin/workflows/${workflowId}/executions/${executionId}/cancel`, {
      method: 'POST',
    }),
  stream: (workflowId: string, executionId: string): AuthenticatedEventSource =>
    createAuthenticatedEventSource(`${API_BASE}/admin/workflows/${workflowId}/executions/${executionId}/stream`),
  getNodeExecutions: async (_workflowId: string, executionId: string) => {
    const data = await apiFetch<{ execution: WorkflowExecution; node_executions: WorkflowNodeExecution[] }>(
      `/admin/workflows/executions/${executionId}`
    );
    return { node_executions: data.node_executions };
  },
  approveNode: (executionId: string, nodeId: string, resolvedBy?: string) =>
    apiFetch<{ message: string; execution_id: string }>(
      `/admin/workflows/executions/${executionId}/nodes/${nodeId}/approve`,
      {
        method: 'POST',
        body: JSON.stringify({ resolved_by: resolvedBy }),
      },
    ),
  rejectNode: (executionId: string, nodeId: string, resolvedBy?: string) =>
    apiFetch<{ message: string; execution_id: string }>(
      `/admin/workflows/executions/${executionId}/nodes/${nodeId}/reject`,
      {
        method: 'POST',
        body: JSON.stringify({ resolved_by: resolvedBy }),
      },
    ),
  listPendingApprovals: () =>
    apiFetch<{
      pending_approvals: Array<{
        execution_id: string;
        node_id: string;
        status: string;
        requested_at: string;
        timeout_seconds: number;
      }>;
    }>('/admin/workflows/pending-approvals'),
};

/**
 * Workflow **design conversation** API — a real LLM chat (resolved from the
 * caller's configured account) that designs a workflow and can finalize it into
 * a workflow + first graph version. Conforms to the `ConversationApi` shape used
 * by `useConversation`, mirroring commandConversationApi / ruleConversationApi.
 */
export const workflowConversationApi = {
  list: () =>
    apiFetch<{
      conversations: { id: string; entity_type: string; status: string; updated_at: string }[];
    }>('/api/workflows/conversations/'),
  listActive: () =>
    apiFetch<{ active_conversations: { conversation_id: string; updated_at: string }[] }>(
      '/api/workflows/conversations/active',
    ),
  start: () =>
    apiFetch<{ conversation_id: string; message: string }>('/api/workflows/conversations/start', {
      method: 'POST',
    }),
  get: (convId: string) =>
    apiFetch<{ id: string; status: string; messages_parsed?: ConversationMessage[] }>(
      `/api/workflows/conversations/${convId}`,
    ),
  sendMessage: (
    convId: string,
    message: string,
    options?: { backend?: string; account_id?: string; model?: string; use_cli_agent?: boolean },
  ) =>
    apiFetch<{ message_id: string; status: string }>(
      `/api/workflows/conversations/${convId}/message`,
      { method: 'POST', body: JSON.stringify({ message, ...options }) },
    ),
  stream: (convId: string, options?: AuthenticatedEventSourceOptions): AuthenticatedEventSource =>
    createAuthenticatedEventSource(
      `${API_BASE}/api/workflows/conversations/${convId}/stream`,
      options,
    ),
  finalize: (convId: string) =>
    apiFetch<{ message: string; workflow_id: string; workflow: Workflow }>(
      `/api/workflows/conversations/${convId}/finalize`,
      { method: 'POST' },
    ),
  resume: (convId: string) =>
    apiFetch<{ message: string; conversation_id: string }>(
      `/api/workflows/conversations/${convId}/resume`,
      { method: 'POST' },
    ),
  abandon: (convId: string) =>
    apiFetch<{ message: string }>(`/api/workflows/conversations/${convId}/abandon`, {
      method: 'POST',
    }),
};
