/**
 * Life-Harness layer-rows + per-bot run-history API client (T-final).
 *
 * Read + toggle only — create / supersede stay in the evolution flow.
 */

import { apiFetch } from './client';

export type HarnessLayerKind = 'h2' | 'h3' | 'h4' | 'h5';
export type HarnessSourceKind = 'manual' | 'template' | 'evolved';

export interface HarnessLayerRow {
  id: string;
  bot_id: string;
  trigger_id: string | null;
  layer: HarnessLayerKind;
  name: string;
  enabled: boolean;
  version: number;
  parent_layer_id: string | null;
  source_kind: HarnessSourceKind;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface HarnessLayersByKind {
  h2: HarnessLayerRow[];
  h3: HarnessLayerRow[];
  h4: HarnessLayerRow[];
  h5: HarnessLayerRow[];
}

export interface RunHistorySnapshot {
  execution_id: string;
  harness_kind: string;
  layer_versions: Record<string, number>;
  applied: boolean;
  created_at: string;
}

export const harnessLayersApi = {
  listForBot: (botId: string, layer?: HarnessLayerKind) => {
    const qs = layer ? `?layer=${layer}` : '';
    return apiFetch<{ bot_id: string; layers: HarnessLayersByKind }>(
      `/admin/bots/${encodeURIComponent(botId)}/harness/layers${qs}`,
    );
  },

  getLayer: (layerId: string) =>
    apiFetch<HarnessLayerRow>(
      `/admin/harness/layers/${encodeURIComponent(layerId)}`,
    ),

  toggle: (layerId: string, enabled: boolean) =>
    apiFetch<HarnessLayerRow>(
      `/admin/harness/layers/${encodeURIComponent(layerId)}`,
      { method: 'PATCH', body: JSON.stringify({ enabled }) },
    ),

  runHistory: (botId: string, limit = 20) =>
    apiFetch<{ bot_id: string; snapshots: RunHistorySnapshot[] }>(
      `/admin/bots/${encodeURIComponent(botId)}/harness/run-history?limit=${limit}`,
    ),
};
