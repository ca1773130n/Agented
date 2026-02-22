import * as smd from 'streaming-markdown';

/**
 * Reusable smd.js streaming parser with rAF-batched writes.
 *
 * Encapsulates the init → write (batched) → finalize lifecycle that was
 * previously duplicated in useConversation and AIBackendsPage.
 *
 * @param options.onFlush - called after each rAF batch is flushed (e.g. scroll-to-bottom)
 */
export function useStreamingParser(options?: { onFlush?: () => void }) {
  let parser: smd.Parser | null = null;
  let pending: string[] = [];
  let rafId: number | null = null;

  function init(container: HTMLElement) {
    while (container.firstChild) {
      container.removeChild(container.firstChild);
    }
    const renderer = smd.default_renderer(container);
    parser = smd.parser(renderer);
  }

  function write(text: string) {
    pending.push(text);
    if (!rafId) {
      rafId = requestAnimationFrame(flush);
    }
  }

  function flush() {
    rafId = null;
    if (!parser || pending.length === 0) return;
    const batch = pending.join('');
    pending = [];
    smd.parser_write(parser, batch);
    options?.onFlush?.();
  }

  function finalize() {
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    if (pending.length > 0 && parser) {
      const batch = pending.join('');
      pending = [];
      smd.parser_write(parser, batch);
    }
    if (parser) {
      smd.parser_end(parser);
      parser = null;
    }
  }

  function destroy() {
    finalize();
  }

  return { init, write, finalize, destroy };
}
