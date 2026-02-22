/**
 * Sketch API module.
 */
import { apiFetch } from './client';
import type { Sketch, SketchStatus } from './types';

export const sketchApi = {
  list: (params?: { status?: SketchStatus; project_id?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.project_id) query.set('project_id', params.project_id);
    const qs = query.toString();
    return apiFetch<{ sketches: Sketch[] }>(`/admin/sketches${qs ? `?${qs}` : ''}`);
  },
  get: (id: string) => apiFetch<Sketch>(`/admin/sketches/${id}`),
  create: (data: { title: string; content?: string; project_id?: string }) =>
    apiFetch<{ message: string; sketch_id: string }>('/admin/sketches', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<Omit<Sketch, 'id' | 'created_at' | 'updated_at'>>) =>
    apiFetch<{ message: string }>(`/admin/sketches/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    apiFetch<{ message: string }>(`/admin/sketches/${id}`, { method: 'DELETE' }),
  classify: (id: string) =>
    apiFetch<{ message: string; classification: Record<string, unknown> }>(`/admin/sketches/${id}/classify`, {
      method: 'POST',
    }),
  route: (id: string) =>
    apiFetch<{ message: string; routing: Record<string, unknown> }>(`/admin/sketches/${id}/route`, {
      method: 'POST',
    }),
};
