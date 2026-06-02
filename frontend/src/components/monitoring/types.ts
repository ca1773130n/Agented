import type { MonitoringStatus, SnapshotHistory } from '../../services/api';

export type RateWindow = '24h' | '48h' | '72h' | '96h' | '120h';

export const rateWindowLabels: Record<RateWindow, string> = {
  '24h': '24h',
  '48h': '48h',
  '72h': '72h',
  '96h': '96h',
  '120h': '120h',
};

// Window type display labels
export const windowTypeLabels: Record<string, string> = {
  five_hour: '5 Hour',
  seven_day: '7 Day',
  seven_day_opus: 'Opus 7 Day',
  seven_day_sonnet: 'Sonnet 7 Day',
  seven_day_oauth_apps: 'OAuth Apps 7 Day',
  seven_day_cowork: 'Cowork 7 Day',
  primary_window: 'Codex 5 Hour',
  secondary_window: 'Codex 7 Day',
  '5h_sliding': 'Opus 5 Hour',
  weekly: 'Opus 7 Day',
  rpd: 'RPD',
  tpm_60s: 'TPM (60s)',
};

export const legacyWindowTypes = new Set(['5h_sliding', 'weekly', 'rpd', 'tpm_60s']);
export const providerWindowTypes = new Set([
  'five_hour',
  'seven_day',
  'seven_day_opus',
  'seven_day_sonnet',
  'seven_day_oauth_apps',
  'seven_day_cowork',
]);
export const backendTypeOrder: Record<string, number> = {
  claude: 0,
  codex: 1,
  gemini: 2,
  opencode: 3,
};

export const backendLabels: Record<string, string> = {
  claude: 'Claude',
  codex: 'Codex',
  gemini: 'Gemini',
  opencode: 'OpenCode',
};

export const gaugeAccentPalette = [
  '#8855ff',
  '#00d4ff',
  '#f59e0b',
  '#e879f9',
  '#10b981',
  '#3b82f6',
];

export interface AccountCard {
  account_id: number;
  account_name: string;
  plan: string;
  backend_type: string;
  windows: MonitoringStatus['windows'];
}

export interface BackendGroup {
  backend_type: string;
  label: string;
  cards: AccountCard[];
}

export interface CombinedHistoryEntry {
  windowType: string;
  label: string;
  history: SnapshotHistory['history'];
  color?: string;
  ratePerHour?: number;
  resetsAt?: string | null;
}
