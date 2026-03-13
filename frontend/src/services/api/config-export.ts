import { apiFetch } from './client';

export interface ConfigExport {
  format: string;
  data: string;
  trigger_count: number;
}

export const configExportApi = {
  exportTrigger: (triggerId: string, format = 'json') =>
    apiFetch<ConfigExport>(`/admin/triggers/${triggerId}/export?format=${format}`),

  exportAll: (format = 'json') =>
    apiFetch<ConfigExport>(`/admin/triggers/export-all?format=${format}`),

  importConfig: (data: { config: string; format: string }) =>
    apiFetch<{ imported: number }>('/admin/triggers/import', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  validateConfig: (data: { config: string; format: string }) =>
    apiFetch<{ valid: boolean; errors: string[] }>('/admin/triggers/validate-config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
