/**
 * Workflow and workflow execution API modules.
 */
import { API_BASE, apiFetch } from './client';
import type {
  Workflow,
  WorkflowVersion,
  WorkflowExecution,
  WorkflowNodeExecution,
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
  stream: (workflowId: string, executionId: string): EventSource =>
    new EventSource(`${API_BASE}/admin/workflows/${workflowId}/executions/${executionId}/stream`),
  getNodeExecutions: async (_workflowId: string, executionId: string) => {
    const data = await apiFetch<{ execution: WorkflowExecution; node_executions: WorkflowNodeExecution[] }>(
      `/admin/workflows/executions/${executionId}`
    );
    return { node_executions: data.node_executions };
  },
};
