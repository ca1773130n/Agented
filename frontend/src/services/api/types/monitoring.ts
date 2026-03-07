/**
 * Monitoring, Backend, Account, and rate-limit types.
 */

export interface MonitoringAccountConfig {
  enabled: boolean;
}

export interface MonitoringConfig {
  enabled: boolean;
  polling_minutes: number;
  accounts: Record<string, MonitoringAccountConfig>;
}

export interface ConsumptionRates {
  '24h': number | null;
  '48h': number | null;
  '72h': number | null;
  '96h': number | null;
  '120h': number | null;
  unit?: string;  // '%/hr' for percentage-only mode, 'tok/hr' otherwise
}

export interface EtaProjection {
  status: 'safe' | 'projected' | 'at_limit' | 'no_data';
  message: string;
  eta: string | null;
  minutes_remaining: number | null;
  resets_at: string | null;
}

export interface WindowSnapshot {
  account_id: number;
  account_name: string;
  plan?: string;
  backend_type: string;
  window_type: string;
  tokens_used: number;
  tokens_limit: number;
  percentage: number;
  threshold_level: string;
  resets_at: string | null;
  recorded_at: string | null;
  consumption_rates: ConsumptionRates;
  eta: EtaProjection;
  shared_with?: string[];
  no_data?: boolean;
}

export interface MonitoringStatus {
  enabled: boolean;
  polling_minutes: number;
  windows: WindowSnapshot[];
  threshold_alerts: Array<{
    account_id: number;
    window_type: string;
    from_level: string;
    to_level: string;
  }>;
}

export interface SnapshotHistoryEntry {
  tokens_used: number;
  percentage: number;
  recorded_at: string;
}

export interface SnapshotHistory {
  account_id: number;
  window_type: string;
  history: SnapshotHistoryEntry[];
}

// AI Backends types
export interface BackendCapabilities {
  supports_json_output: boolean;
  supports_token_usage: boolean;
  supports_streaming: boolean;
  supports_non_interactive: boolean;
  json_output_flag?: string;
  non_interactive_flag?: string;
}

export interface AIBackend {
  id: string;
  name: string;
  type: string;  // 'claude', 'opencode', 'gemini', 'codex'
  description?: string;
  icon?: string;
  documentation_url?: string;
  is_installed: number;
  version?: string;
  models?: string[];  // Parsed from JSON
  capabilities?: BackendCapabilities;
  cli_path?: string;
  account_count?: number;
  account_emails?: string;  // Comma-separated emails from all accounts
  created_at?: string;
  last_used_at?: string;  // MAX(last_used_at) across all accounts
}

export interface RateLimitWindow {
  window_type: string;
  percentage: number;
  resets_at: string | null;
  tokens_used: number;
  tokens_limit: number;
}

export interface BackendAccount {
  id: number;
  backend_id: string;
  account_name: string;
  email?: string;
  config_path?: string;
  api_key_env?: string;
  is_default: number;
  plan?: string;
  usage_data?: Record<string, unknown>;
  created_at?: string;
}

export interface AIBackendWithAccounts extends AIBackend {
  accounts: BackendAccount[];
}
