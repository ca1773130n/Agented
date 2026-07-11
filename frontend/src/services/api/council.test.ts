import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { councilApi } from './council';
import type { CouncilEvent } from './council';

vi.mock('./client', () => ({ getApiKey: () => 'test-key' }));

/** Build a Response whose body streams the given byte chunks as an SSE stream. */
function streamResponse(chunks: string[], ok = true, status = 200): Response {
  const enc = new TextEncoder();
  let i = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) controller.enqueue(enc.encode(chunks[i++]));
      else controller.close();
    },
  });
  return { ok, status, body } as unknown as Response;
}

function frame(ev: CouncilEvent): string {
  return `event: council\ndata: ${JSON.stringify(ev)}\n\n`;
}

describe('councilApi.convene', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()));
  afterEach(() => vi.unstubAllGlobals());

  it('POSTs the council request with Bearer auth + defaults', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(streamResponse([]));
    await councilApi.convene({ question: 'q', options: ['a', 'b'] }, { onEvent: () => {} });
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/api/v1/council/');
    expect(init.method).toBe('POST');
    expect(init.headers.Authorization).toBe('Bearer test-key');
    expect(JSON.parse(init.body)).toEqual({ question: 'q', options: ['a', 'b'], context: '', rounds: 1 });
  });

  it('clamps rounds to the server 0-5 int range (blank/out-of-range → default)', async () => {
    // Fresh response per call — a ReadableStream can only be read once.
    (fetch as ReturnType<typeof vi.fn>).mockImplementation(() => Promise.resolve(streamResponse([])));
    // '' (a cleared number input) is not finite → default 1
    await councilApi.convene(
      { question: 'q', options: ['a', 'b'], rounds: '' as unknown as number },
      { onEvent: () => {} },
    );
    expect(JSON.parse((fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body).rounds).toBe(1);
    // 9 (manual over-max entry) → clamped to 5
    await councilApi.convene({ question: 'q', options: ['a', 'b'], rounds: 9 }, { onEvent: () => {} });
    expect(JSON.parse((fetch as ReturnType<typeof vi.fn>).mock.calls[1][1].body).rounds).toBe(5);
  });

  it('parses each SSE frame into a CouncilEvent and fires onDone', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      streamResponse([
        frame({ kind: 'council_start', payload: { members: [{ role: 'pragmatist' }] } }),
        frame({ kind: 'position', role: 'pragmatist', text: 'go with A' }),
        frame({ kind: 'votes', payload: { tally: { A: 2, B: 1 } } }),
        frame({ kind: 'decision', payload: { choice: 1, choice_label: 'A', rationale: 'strongest' } }),
      ]),
    );
    const got: CouncilEvent[] = [];
    const onDone = vi.fn();
    await councilApi.convene({ question: 'q', options: ['A', 'B'] }, { onEvent: (e) => got.push(e), onDone });
    expect(got.map((e) => e.kind)).toEqual(['council_start', 'position', 'votes', 'decision']);
    expect(got[3].payload?.choice_label).toBe('A');
    expect(onDone).toHaveBeenCalledOnce();
  });

  it('reassembles a frame split across two chunks (buffering)', async () => {
    const f = frame({ kind: 'position', role: 'skeptic', text: 'careful' });
    const mid = Math.floor(f.length / 2);
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(streamResponse([f.slice(0, mid), f.slice(mid)]));
    const got: CouncilEvent[] = [];
    await councilApi.convene({ question: 'q', options: ['A', 'B'] }, { onEvent: (e) => got.push(e) });
    expect(got).toHaveLength(1);
    expect(got[0].text).toBe('careful');
  });

  it('surfaces a non-OK response via onError (no stream)', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(streamResponse([], false, 500));
    const onError = vi.fn();
    await councilApi.convene({ question: 'q', options: ['A', 'B'] }, { onEvent: () => {}, onError });
    expect(onError).toHaveBeenCalledWith('council failed (500)');
  });

  it('ignores a malformed data frame rather than aborting the debate', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      streamResponse([
        'event: council\ndata: {not json\n\n',
        frame({ kind: 'decision', payload: { choice_label: 'B' } }),
      ]),
    );
    const got: CouncilEvent[] = [];
    const onDone = vi.fn();
    await councilApi.convene({ question: 'q', options: ['A', 'B'] }, { onEvent: (e) => got.push(e), onDone });
    expect(got.map((e) => e.kind)).toEqual(['decision']); // malformed skipped, valid kept
    expect(onDone).toHaveBeenCalledOnce();
  });
});
