/**
 * Project instance API module.
 */
import { apiFetch } from './client';
import type {
  ProjectSAInstance,
  CreateInstanceRequest,
  CreateInstanceResponse,
} from './types/project-instances';

export const projectInstanceApi = {
  list: (projectId: string) =>
    apiFetch<{ instances: ProjectSAInstance[] }>(`/admin/projects/${projectId}/instances`),

  get: (projectId: string, instanceId: string) =>
    apiFetch<ProjectSAInstance>(`/admin/projects/${projectId}/instances/${instanceId}`),

  create: (projectId: string, data: CreateInstanceRequest) =>
    apiFetch<CreateInstanceResponse>(`/admin/projects/${projectId}/instances`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  delete: (projectId: string, instanceId: string) =>
    apiFetch<{ message: string }>(`/admin/projects/${projectId}/instances/${instanceId}`, {
      method: 'DELETE',
    }),
};
