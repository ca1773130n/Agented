/**
 * Council mode (ai-accounts 0.4.5+) — convene a debating panel of your AI
 * accounts to decide a question. The endpoint lives on the ai-accounts sidecar
 * (`POST /api/v1/council/`, Vite-proxied to :20001) and streams the debate as
 * SSE (`event: council`, one CouncilEvent per frame). Native EventSource is
 * GET-only, so we drive a fetch stream reader — mirroring sketches.ts.
 *
 * Auth matches the shared AiAccountsClient (main.ts): `Authorization: Bearer
 * <apiKey>` sourced from sessionStorage via getApiKey().
 */
import { getApiKey } from './client';

export interface CouncilRequest {
  question: string;
  options: string[]; // 2-10
  context?: string;
  rounds?: number; // 0-5
}

/** One streamed council event. Mirrors ai_accounts_core CouncilEvent. */
export interface CouncilEvent {
  kind:
    | 'council_start'
    | 'position'
    | 'rebuttal'
    | 'member_error'
    | 'votes'
    | 'decision'
    | 'council_error';
  role?: string | null; // member lens ("pragmatist", …)
  backend_kind?: string | null;
  account_label?: string | null;
  round?: number | null; // rebuttal round (1-based)
  text?: string | null; // position/rebuttal text
  option?: number | null; // member's 1-based vote
  error?: string | null;
  payload?: Record<string, unknown> | null; // roster / votes tally / decision
}

export interface CouncilHandlers {
  onEvent: (event: CouncilEvent) => void;
  onError?: (message: string) => void;
  onDone?: () => void;
  signal?: AbortSignal;
}

export const councilApi = {
  /**
   * Convene the council and stream its debate. Resolves when the stream ends
   * (onDone) or errors (onError); individual events flow through onEvent.
   */
  convene: async (req: CouncilRequest, handlers: CouncilHandlers): Promise<void> => {
    let resp: Response;
    try {
      const key = getApiKey();
      resp = await fetch('/api/v1/council/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(key ? { Authorization: `Bearer ${key}` } : {}),
        },
        credentials: 'include',
        body: JSON.stringify({
          question: req.question,
          options: req.options,
          context: req.context ?? '',
          // Clamp to the server's ge=0/le=5 int range so a blank/out-of-range
          // input degrades to the default 1 instead of a msgspec 400.
          rounds: Number.isFinite(req.rounds)
            ? Math.max(0, Math.min(5, Math.trunc(req.rounds as number)))
            : 1,
        }),
        signal: handlers.signal,
      });
    } catch (e) {
      handlers.onError?.(e instanceof Error ? e.message : 'council request failed');
      return;
    }
    if (!resp.ok || !resp.body) {
      handlers.onError?.(`council failed (${resp.status})`);
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const frames = buf.split('\n\n');
        buf = frames.pop() ?? ''; // keep the trailing partial frame
        for (const frame of frames) {
          let dataStr = '';
          for (const line of frame.split('\n')) {
            // We only emit `event: council`; collect the data payload.
            if (line.startsWith('data:')) dataStr += line.slice(5).trim();
          }
          if (!dataStr) continue;
          try {
            handlers.onEvent(JSON.parse(dataStr) as CouncilEvent);
          } catch {
            // ignore a malformed frame rather than aborting the whole debate
          }
        }
      }
      handlers.onDone?.();
    } catch (e) {
      // AbortError (user cancelled) is expected — surface others.
      if ((e as Error)?.name !== 'AbortError') {
        handlers.onError?.(e instanceof Error ? e.message : 'council stream error');
      } else {
        handlers.onDone?.();
      }
    }
  },
};
