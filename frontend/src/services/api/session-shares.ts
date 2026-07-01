/**
 * Session live-share / co-drive API module (Phase 25).
 *
 * The OWNER mints/revokes scoped share tokens for a running session
 * (X-API-Key gated). A teammate attaches read-only over SSE with the token
 * (see `createAuthenticatedEventSource('/api/shared-sessions/{token}/stream')`),
 * and a chat-scope teammate co-drives via `coDrive` (25-02) — which is
 * policy-checked server-side before it reaches the operator's session.
 */
import { apiFetch } from './client';

export type ShareScope = 'read' | 'chat';

export interface MintShareResponse {
  token: string;
  scope: ShareScope;
  expires_at: string | null;
}

export interface CoDriveResponse {
  sent: boolean;
  actor_user_id: string;
}

export const sessionShareApi = {
  /** Mint a scoped share token for a running session (owner action). */
  mint: (
    projectId: string,
    sessionId: string,
    scope: ShareScope = 'read',
    ttlSeconds?: number,
  ) =>
    apiFetch<MintShareResponse>(
      `/api/projects/${projectId}/sessions/${sessionId}/share`,
      {
        method: 'POST',
        body: JSON.stringify(
          ttlSeconds != null ? { scope, ttl_seconds: ttlSeconds } : { scope },
        ),
      },
    ),

  /** Revoke a previously minted share token (owner action). */
  revoke: (projectId: string, sessionId: string, token: string) =>
    apiFetch<{ revoked: boolean }>(
      `/api/projects/${projectId}/sessions/${sessionId}/share/${token}`,
      { method: 'DELETE' },
    ),

  /**
   * Co-drive: a chat-scope teammate's message is sent to the operator's running
   * session (25-02). The token is the credential; the server policy-checks the
   * message before it reaches stdin, so a DENY surfaces as an error here.
   *
   * The token is ALSO sent in the `X-Share-Token` header (not just the URL path):
   * the server rejects a co-drive POST that lacks it, which defeats a cross-site
   * forged POST that merely knows a leaked share URL (a cross-origin request
   * cannot set this custom header without a CORS preflight the server denies).
   */
  coDrive: (token: string, text: string) =>
    apiFetch<CoDriveResponse>(`/api/shared-sessions/${token}/send`, {
      method: 'POST',
      headers: { 'X-Share-Token': token },
      body: JSON.stringify({ text }),
    }),
};
