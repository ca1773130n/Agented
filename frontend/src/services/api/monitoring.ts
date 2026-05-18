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
  pollNow: (opts?: { timeout?: number }) => apiFetch<MonitoringStatus>('/admin/monitoring/poll', { method: 'POST', timeout: opts?.timeout }),
  getHistory: (accountId: number, windowType: string, minutes?: number) =>
    apiFetch<SnapshotHistory>(
      `/admin/monitoring/history?account_id=${accountId}&window_type=${windowType}${minutes ? `&minutes=${minutes}` : ''}`
    ),
  // Per-account OAuth credential status — used by the Token Usage
  // Dashboard banner and the AI Backends row badge to flag accounts
  // the poller can't resolve a token for (so the dashboard isn't
  // silently missing rows).
  getCredentials: () =>
    apiFetch<{ accounts: CredentialStatusRow[] }>('/admin/monitoring/credentials'),
};

export interface CredentialStatusRow {
  account_id: number;
  account_name: string | null;
  backend_type: string;
  config_path: string | null;
  credential_status: 'ok' | 'missing' | 'unsupported';
  remediation: string | null;
  expected_location: string | null;
}
