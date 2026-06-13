import type {
  ConsumptionRates,
  EtaProjection,
  MonitoringStatus,
  WindowSnapshot,
} from '../../services/api';
import {
  backendLabels,
  backendTypeOrder,
  gaugeAccentPalette,
  legacyWindowTypes,
  providerWindowTypes,
  windowTypeLabels,
  type AccountCard,
  type BackendGroup,
  type RateWindow,
} from './types';

function geminiModelOrder(windowType: string): number {
  if (windowType.includes('gemini-3-pro')) return 0;
  if (windowType.includes('gemini-3-flash')) return 1;
  if (windowType.includes('gemini-2.5-pro')) return 2;
  if (windowType.includes('gemini-2.5')) return 3;
  if (windowType.includes('gemini-2')) return 4;
  return 5;
}

function sortWindows(
  windows: MonitoringStatus['windows'],
  backendType: string,
): MonitoringStatus['windows'] {
  return [...windows].sort((a, b) => {
    if (backendType === 'gemini') {
      return geminiModelOrder(a.window_type) - geminiModelOrder(b.window_type);
    }
    return a.window_type.localeCompare(b.window_type);
  });
}

export function getGaugeAccentColor(
  backendType: string,
  _windowType: string,
  index: number,
): string {
  if (backendType === 'claude') return '';
  return gaugeAccentPalette[index % gaugeAccentPalette.length];
}

export function getGaugeLabel(
  windowType: string,
  parseWindowType: (s: string) => { model: string; window: string },
): string {
  const { model, window: win } = parseWindowType(windowType);
  const parts: string[] = [];
  if (model) parts.push(`<span class="gauge-model">${model}</span>`);
  if (win) parts.push(`<span class="gauge-window">${win}</span>`);
  return parts.join('') || windowType;
}

export function getWindowLabel(
  windowType: string,
  parseWindowType: (s: string) => { model: string; window: string },
): string {
  if (windowTypeLabels[windowType]) return windowTypeLabels[windowType];
  const { model, window: win } = parseWindowType(windowType);
  return [model, win].filter(Boolean).join(' ') || windowType;
}

export function getTrendKey(accountId: number, windowType: string): string {
  return `${accountId}_${windowType}`;
}

export function getRateWindowMinutes(rw: RateWindow): number {
  switch (rw) {
    case '24h':
      return 1440;
    case '48h':
      return 2880;
    case '72h':
      return 4320;
    case '96h':
      return 5760;
    case '120h':
      return 7200;
    default:
      return 1440;
  }
}

export function formatRate(rates: ConsumptionRates | undefined, rw: RateWindow): string {
  if (!rates) return '--';
  const val = rates[rw];
  if (val == null) return '--';
  const unit = rates.unit;
  if (unit === '%/hr') {
    return `${val.toFixed(1)}%/hr`;
  }
  if (val >= 1000) return `${(val / 1000).toFixed(1)}k tok/hr`;
  return `${Math.round(val)} tok/hr`;
}

export function isRateAvailable(rates: ConsumptionRates | undefined, rw: RateWindow): boolean {
  if (!rates) return false;
  return rates[rw] != null;
}

export function formatRelativeReset(resetsAt: string): string {
  const resetTime = new Date(resetsAt).getTime();
  const now = Date.now();
  const diffMs = resetTime - now;
  if (diffMs <= 0) return 'now';
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 60) return `${diffMin}m`;
  const days = Math.floor(diffMin / 1440);
  const hours = Math.floor((diffMin % 1440) / 60);
  const mins = diffMin % 60;
  if (days > 0) {
    return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
  }
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

export function getResetUrgency(resetsAt: string): 'soon' | 'normal' {
  const resetTime = new Date(resetsAt).getTime();
  const diffMin = (resetTime - Date.now()) / 60000;
  return diffMin <= 30 ? 'soon' : 'normal';
}

export function formatDepletion(eta: EtaProjection): string {
  if (!eta || eta.minutes_remaining == null) return 'Unknown';
  const totalMin = Math.floor(eta.minutes_remaining);
  if (totalMin <= 0) return 'Now';
  const d = Math.floor(totalMin / 1440);
  const h = Math.floor((totalMin % 1440) / 60);
  const m = totalMin % 60;
  if (d > 0) return h > 0 ? `${d}d ${h}h` : `${d}d`;
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`;
  return `${m}m`;
}

export function depletionUrgencyClass(eta: EtaProjection): string {
  if (!eta) return 'unknown';
  return eta.status || 'unknown';
}

export function toRatePctPerHour(w: WindowSnapshot, rw: RateWindow): number | undefined {
  const rates = w.consumption_rates;
  const raw = rates?.[rw];
  if (raw == null) return undefined;
  // If unit is tok/hr, convert to %/hr using tokens_limit
  if (rates?.unit === 'tok/hr' && w.tokens_limit > 0) {
    return (raw / w.tokens_limit) * 100;
  }
  return raw; // already %/hr
}

export function buildAccountCards(status: MonitoringStatus | null): AccountCard[] {
  if (!status?.windows?.length) return [];
  const grouped: Record<
    number,
    { account_name: string; plan: string; backend_type: string; windows: MonitoringStatus['windows'] }
  > = {};
  for (const w of status.windows) {
    if (!grouped[w.account_id]) {
      grouped[w.account_id] = {
        account_name: w.account_name,
        plan: w.plan || '',
        backend_type: w.backend_type,
        windows: [],
      };
    }
    grouped[w.account_id].windows.push(w);
  }
  const cards = Object.entries(grouped)
    .map(([id, data]) => {
      const hasProvider = data.windows.some(
        (w) => providerWindowTypes.has(w.window_type) || w.window_type.endsWith('_window'),
      );
      const filtered = hasProvider
        ? data.windows.filter((w) => !legacyWindowTypes.has(w.window_type))
        : data.windows;
      return {
        account_id: Number(id),
        account_name: data.account_name,
        plan: data.plan,
        backend_type: data.backend_type,
        windows: sortWindows(filtered, data.backend_type),
      };
    })
    .sort((a, b) => {
      const typeA = backendTypeOrder[a.backend_type] ?? 99;
      const typeB = backendTypeOrder[b.backend_type] ?? 99;
      if (typeA !== typeB) return typeA - typeB;
      return a.account_name.localeCompare(b.account_name);
    });
  return cards;
}

export function groupCardsByBackend(cards: AccountCard[]): BackendGroup[] {
  const groups: BackendGroup[] = [];
  let currentType = '';
  let currentGroup: AccountCard[] = [];
  for (const card of cards) {
    if (card.backend_type !== currentType) {
      if (currentGroup.length > 0) {
        groups.push({
          backend_type: currentType,
          label: backendLabels[currentType] || currentType,
          cards: currentGroup,
        });
      }
      currentType = card.backend_type;
      currentGroup = [];
    }
    currentGroup.push(card);
  }
  if (currentGroup.length > 0) {
    groups.push({
      backend_type: currentType,
      label: backendLabels[currentType] || currentType,
      cards: currentGroup,
    });
  }
  return groups;
}
