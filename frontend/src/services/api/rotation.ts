/**
 * Rotation dashboard API module.
 */
import { apiFetch } from './client';
import type { RotationDashboardStatus, RotationHistoryResponse } from './types';

export const rotationApi = {
  getStatus: () => apiFetch<RotationDashboardStatus>('/admin/rotation/status'),
  getHistory: (executionId?: string, limit?: number) =>
    apiFetch<RotationHistoryResponse>(
      `/admin/rotation/history?${executionId ? `execution_id=${executionId}&` : ''}limit=${limit || 50}`
    ),
};
