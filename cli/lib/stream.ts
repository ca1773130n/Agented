/**
 * SSE streaming.
 *
 * Several of the most useful endpoints are Server-Sent Events (execution logs,
 * chat, traces, super-agent sessions). Rendering rule, matching the rest of the
 * CLI: on a TTY the frames are pretty-printed for a human; when piped, each
 * frame is emitted as one line of NDJSON so `| jq` works per event rather than
 * waiting for a stream that never ends.
 *
 * Ctrl-C aborts cleanly (exit 130) instead of dumping a stack.
 */

import { buildRequest, type RequestOpts } from './transport.ts';
import { out, note, isTTY } from './output.ts';

export interface Frame {
  event?: string;
  data: string;
  id?: string;
}

/** Incremental SSE parser: feed it chunks, get whole frames. */
export class SSEParser {
  private buf = '';

  push(chunk: string): Frame[] {
    this.buf += chunk;
    const frames: Frame[] = [];
    // Frames are separated by a blank line; tolerate both \n\n and \r\n\r\n.
    let idx: number;
    while ((idx = this.findSeparator()) >= 0) {
      const raw = this.buf.slice(0, idx);
      this.buf = this.buf.slice(idx).replace(/^(\r?\n){2}/, '');
      const f = parseFrame(raw);
      if (f) frames.push(f);
    }
    return frames;
  }

  private findSeparator(): number {
    const a = this.buf.indexOf('\n\n');
    const b = this.buf.indexOf('\r\n\r\n');
    if (a < 0) return b;
    if (b < 0) return a;
    return Math.min(a, b);
  }

  /** Anything left when the stream ends (a final frame without a trailing blank line). */
  flush(): Frame[] {
    const rest = this.buf.trim();
    this.buf = '';
    const f = rest ? parseFrame(rest) : null;
    return f ? [f] : [];
  }
}

export function parseFrame(raw: string): Frame | null {
  const lines = raw.split(/\r?\n/);
  const data: string[] = [];
  let event: string | undefined;
  let id: string | undefined;
  for (const line of lines) {
    if (!line || line.startsWith(':')) continue; // comment / heartbeat
    const colon = line.indexOf(':');
    const field = colon < 0 ? line : line.slice(0, colon);
    const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
    if (field === 'data') data.push(value);
    else if (field === 'event') event = value;
    else if (field === 'id') id = value;
  }
  if (!data.length && !event) return null;
  return { event, data: data.join('\n'), id };
}

export interface StreamResult {
  frames: number;
}

/**
 * Open an SSE endpoint and render frames until the server closes it or the user
 * interrupts. Returns the frame count so a caller (or a smoke test) can assert
 * that something actually arrived.
 */
export async function stream(o: RequestOpts & { limit?: number }): Promise<StreamResult> {
  const built = buildRequest(o);
  const ctl = new AbortController();
  const onSigint = () => ctl.abort();
  process.on('SIGINT', onSigint);

  let frames = 0;
  try {
    const res = await fetch(built.url, {
      method: built.method,
      headers: { ...built.headers, Accept: 'text/event-stream' },
      body: built.body === undefined ? undefined : JSON.stringify(built.body),
      signal: ctl.signal,
    });
    if (res.status >= 400) {
      note(`HTTP ${res.status} from ${built.url}`);
      return { frames: 0 };
    }
    if (!res.body) return { frames: 0 };

    note(isTTY ? `streaming ${built.url} — Ctrl-C to stop` : '');
    const parser = new SSEParser();
    const decoder = new TextDecoder();
    for await (const chunk of res.body as unknown as AsyncIterable<Uint8Array>) {
      for (const f of parser.push(decoder.decode(chunk, { stream: true }))) {
        render(f);
        frames++;
        if (o.limit && frames >= o.limit) return { frames };
      }
    }
    for (const f of parser.flush()) {
      render(f);
      frames++;
    }
  } catch (e) {
    if (!(e instanceof Error && e.name === 'AbortError')) throw e;
  } finally {
    process.off('SIGINT', onSigint);
  }
  return { frames };
}

function render(f: Frame): void {
  if (isTTY) {
    const label = f.event ? `[${f.event}] ` : '';
    out(label + f.data);
  } else {
    // NDJSON: one self-describing object per line, never a buffered array.
    let parsed: unknown = f.data;
    try {
      parsed = JSON.parse(f.data);
    } catch {
      /* keep as string */
    }
    out(JSON.stringify({ event: f.event ?? null, data: parsed }));
  }
}
