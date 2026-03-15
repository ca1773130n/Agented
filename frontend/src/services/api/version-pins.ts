/**
 * Version pin management API module.
 */
import { apiFetch } from './client';

export type PinStatus = 'pinned' | 'unpinned' | 'outdated';
export type ComponentType = 'skill' | 'plugin';

export interface VersionPin {
  id: string;
  component_type: ComponentType;
  component_id: string;
  component_name: string;
  pinned_version: string | null;
  latest_version: string | null;
  bot_id: string | null;
  bot_name: string | null;
  status: PinStatus;
  pinned_at: string | null;
  changelog: string | null;
}

export interface ComponentVersionHistory {
  id: number;
  component_id: string;
  version: string;
  released_at: string | null;
  breaking: number | boolean;
  summary: string | null;
}

export interface VersionPinsListResponse {
  pins: VersionPin[];
  total: number;
}

export interface VersionHistoryResponse {
  history: ComponentVersionHistory[];
  total: number;
}

export interface UpgradeAllResponse {
  upgraded: number;
  total_outdated: number;
}

export const versionPinsApi = {
  listPins: () =>
    apiFetch<VersionPinsListResponse>('/admin/version-pins/'),

  updatePin: (pinId: string, data: {
    pinned_version: string;
    status?: string;
    pinned_at?: string;
  }) =>
    apiFetch<VersionPin>(`/admin/version-pins/${pinId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  unpinPin: (pinId: string) =>
    apiFetch<VersionPin>(`/admin/version-pins/${pinId}/unpin`, {
      method: 'POST',
    }),

  upgradeAll: () =>
    apiFetch<UpgradeAllResponse>('/admin/version-pins/upgrade-all', {
      method: 'POST',
    }),

  getVersionHistory: (componentId: string) =>
    apiFetch<VersionHistoryResponse>(`/admin/version-pins/${componentId}/versions`),
};
