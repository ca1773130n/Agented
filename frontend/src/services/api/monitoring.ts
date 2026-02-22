/**
 * Monitoring API module.
 */
import { apiFetch } from './client';
import type {
  MonitoringConfig,
  MonitoringStatus,
  SnapshotHistory,
} from './types';

// Monitoring API
export const monitoringApi = {
  getConfig: () => apiFetch<MonitoringConfig>('/admin/monitoring/config'),
  setConfig: (config: MonitoringConfig) =>
    apiFetch<MonitoringConfig>('/admin/monitoring/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }),
  getStatus: () => apiFetch<MonitoringStatus>('/admin/monitoring/status'),
  pollNow: () => apiFetch<MonitoringStatus>('/admin/monitoring/poll', { method: 'POST' }),
  getHistory: (accountId: number, windowType: string, minutes?: number) =>
    apiFetch<SnapshotHistory>(
      `/admin/monitoring/history?account_id=${accountId}&window_type=${windowType}${minutes ? `&minutes=${minutes}` : ''}`
    ),
};
