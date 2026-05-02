/**
 * Tour boot-time guard prefetch (Plan 01-02).
 *
 * Calls the backend's aggregate `/health/setup-status` endpoint (added in
 * Plan 01-01) and maps the response into a typed shape the tour machine
 * can consume. Public; no auth required.
 *
 * The endpoint is intentionally non-blocking: when it's unreachable we
 * return a sentinel "unknown" object so the tour treats the install as
 * fresh rather than hanging on a network spinner.
 */
import type { StepId } from './machine'

export interface SetupStatus {
  instanceId: string | null
  completed: Record<StepId, boolean>
  /** True when the call failed; caller should treat the install as fresh. */
  unknown: boolean
}

interface SetupStatusResponse {
  instance_id: string | null
  has_workspace: boolean
  has_claude_account: boolean
  has_codex_account: boolean
  has_gemini_account: boolean
  has_opencode_account: boolean
  has_harness_synced: boolean
  has_first_product: boolean
}

const UNKNOWN: SetupStatus = {
  instanceId: null,
  completed: {
    workspace: false,
    claude: false,
    codex: false,
    gemini: false,
    opencode: false,
    monitoring: false,
    harness: false,
    product: false,
  },
  unknown: true,
}

/**
 * Maps the API response to the StepId-keyed completion object the machine
 * uses. `monitoring` has no API-side guard (it's a read-only step) so it
 * stays `false` and the user always sees it.
 */
export function deriveCompleted(
  payload: SetupStatusResponse,
): Record<StepId, boolean> {
  return {
    workspace: payload.has_workspace,
    claude: payload.has_claude_account,
    codex: payload.has_codex_account,
    gemini: payload.has_gemini_account,
    opencode: payload.has_opencode_account,
    monitoring: false,
    harness: payload.has_harness_synced,
    product: payload.has_first_product,
  }
}

export async function fetchSetupStatus(
  fetchFn: typeof fetch = fetch,
): Promise<SetupStatus> {
  try {
    const resp = await fetchFn('/health/setup-status', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
    if (!resp.ok) return UNKNOWN
    const payload = (await resp.json()) as SetupStatusResponse
    return {
      instanceId: payload.instance_id,
      completed: deriveCompleted(payload),
      unknown: false,
    }
  } catch {
    return UNKNOWN
  }
}
