/**
 * v0.7.0: Bot Health & SLA dashboard API client.
 *
 * Wraps GET /admin/bots/health which returns per-bot rollups
 * (success rate, p50/p95/p99, last failure, status pill) for
 * a sliding window of 1..90 days (default 7).
 */
import { apiFetch } from './client';

export type BotHealthStatus = 'healthy' | 'degraded' | 'down' | 'no_recent_runs';

export interface BotHealthRollup {
  bot_id: string;
  bot_name: string;
  success_count: number;
  fail_count: number;
  success_rate: number | null;
  p50_duration_ms: number | null;
  p95_duration_ms: number | null;
  p99_duration_ms: number | null;
  last_run_at: string | null;
  last_failure_at: string | null;
  last_failure_message: string | null;
  status_pill: BotHealthStatus;
}

export interface BotHealthResponse {
  window_days: number;
  rollups: BotHealthRollup[];
}

export const botHealthApi = {
  list(windowDays: number = 7): Promise<BotHealthResponse> {
    return apiFetch<BotHealthResponse>(
      `/admin/bots/health?window_days=${windowDays}`,
    );
  },
};
