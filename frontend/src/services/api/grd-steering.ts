/**
 * GRD 0.5.0 research-steering settings, per project.
 *
 * These are NOT Agented settings-table keys — they are read from and written to
 * the project's own `<local_path>/.planning/config.json`, which is the file GRD
 * itself reads. A toggle stored anywhere else would change nothing about how
 * GRD behaves.
 *
 * The two travel together because one gates the other: while `autonomous_mode`
 * is true, GRD's `resolveInteractive` returns `active:false` and the human
 * checkpoints never fire, so `interactive_fallback` — who answers when no human
 * is present — is the only one of the pair that does anything.
 */

import { apiFetch } from './client';

/** The only two values GRD accepts; anything else it warns about and treats as 'recommended'. */
export type InteractiveFallback = 'recommended' | 'panel';

export interface GrdSteeringProject {
  project_id: string;
  project_name: string;
  local_path: string | null;
  /** Absolute path of the config we read, or null when the project has no local path. */
  config_path: string | null;
  /**
   * False when there is no readable `.planning/config.json` (no local path, GRD
   * never initialised, or the file is corrupt). The UI must disable the controls
   * rather than offer a write that will fail — we deliberately never create the
   * file, since that would define every other GRD setting by omission.
   */
  configured: boolean;
  /** While true, the human checkpoints never fire — the fallback answers instead. */
  autonomous_mode: boolean;
  /**
   * `research_gates.interactive.enabled`. Read-only here, but without it the UI
   * would show a fallback that does nothing: GRD only consults the fallback for
   * a checkpoint it was going to raise.
   */
  interactive_enabled: boolean;
  interactive_fallback: InteractiveFallback;
}

export interface GrdSteeringPatch {
  autonomous_mode?: boolean;
  interactive_fallback?: InteractiveFallback;
}

export const grdSteeringApi = {
  list: () =>
    apiFetch<{ projects: GrdSteeringProject[] }>('/admin/system/grd/steering/projects'),

  /** Patch either or both settings. At least one is required — the backend
   *  rejects an empty patch rather than returning a 200 that changed nothing. */
  set: (projectId: string, patch: GrdSteeringPatch) =>
    apiFetch<{ project: GrdSteeringProject }>(
      `/admin/system/grd/steering/projects/${encodeURIComponent(projectId)}`,
      { method: 'POST', body: JSON.stringify(patch) },
    ),
};
