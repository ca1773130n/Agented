/**
 * Scheduler API module — agent execution admission control.
 */
import { apiFetch } from './client';
import type { SchedulerStatus } from './types';

export const schedulerApi = {
  getStatus: () => apiFetch<SchedulerStatus>('/admin/scheduler/status'),
  getSessions: () =>
    apiFetch<{ sessions: SchedulerStatus['sessions'] }>('/admin/scheduler/sessions'),
  getEligibility: (accountId: number) =>
    apiFetch<{ eligible: boolean; reason: string; message?: string; resume_estimate?: string }>(
      `/admin/scheduler/eligibility/${accountId}`
    ),
};
