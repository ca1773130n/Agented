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
  // Batch history: one request for many windows. The Cost dashboard needs a
  // history per window per account (~12-36 series); firing them as individual
  // getHistory() calls bursts past the 30/min admin rate limit → 429 storm →
  // blank trend charts. This collapses them into a single POST.
  getHistoryBatch: (
    windows: { account_id: number; window_type: string }[],
    minutes?: number,
  ) =>
    apiFetch<{ histories: Record<string, SnapshotHistory> }>(
      '/admin/monitoring/history-batch',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ windows, minutes }),
      },
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
