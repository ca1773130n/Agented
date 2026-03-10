import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock streaming-markdown
const mockParserWrite = vi.fn();
const mockParserEnd = vi.fn();
const mockParser = vi.fn().mockReturnValue({ id: 'mock-parser' });
const mockDefaultRenderer = vi.fn().mockReturnValue({ id: 'mock-renderer' });

vi.mock('streaming-markdown', () => ({
  parser: (renderer: unknown) => mockParser(renderer),
  default_renderer: (container: unknown) => mockDefaultRenderer(container),
  parser_write: (p: unknown, text: string) => mockParserWrite(p, text),
  parser_end: (p: unknown) => mockParserEnd(p),
}));

import { useStreamingParser } from '../useStreamingParser';

describe('useStreamingParser', () => {
  let rafCallbacks: (() => void)[];

  beforeEach(() => {
    vi.clearAllMocks();
    rafCallbacks = [];

    // Mock requestAnimationFrame to capture callbacks
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      rafCallbacks.push(cb as () => void);
      return rafCallbacks.length;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('init creates a parser and renderer for the container', () => {
    const { init } = useStreamingParser();
    const container = document.createElement('div');

    init(container);

    expect(mockDefaultRenderer).toHaveBeenCalledWith(container);
    expect(mockParser).toHaveBeenCalled();
  });

  it('init clears existing children from the container', () => {
    const { init } = useStreamingParser();
    const container = document.createElement('div');
    container.appendChild(document.createElement('span'));
    container.appendChild(document.createElement('p'));

    expect(container.childNodes.length).toBe(2);
    init(container);
    expect(container.childNodes.length).toBe(0);
  });

  it('write batches text and flushes on rAF', () => {
    const { init, write } = useStreamingParser();
    const container = document.createElement('div');
    init(container);

    write('hello ');
    write('world');

    expect(mockParserWrite).not.toHaveBeenCalled();

    // Flush rAF
    rafCallbacks.forEach((cb) => cb());

    expect(mockParserWrite).toHaveBeenCalledTimes(1);
    expect(mockParserWrite).toHaveBeenCalledWith(expect.anything(), 'hello world');
  });

  it('finalize flushes pending writes and ends parser', () => {
    const { init, write, finalize } = useStreamingParser();
    const container = document.createElement('div');
    init(container);

    write('pending text');
    finalize();

    expect(mockParserWrite).toHaveBeenCalledWith(expect.anything(), 'pending text');
    expect(mockParserEnd).toHaveBeenCalled();
  });

  it('finalize cancels pending rAF', () => {
    const { init, write, finalize } = useStreamingParser();
    const container = document.createElement('div');
    init(container);

    write('text');
    finalize();

    expect(window.cancelAnimationFrame).toHaveBeenCalled();
  });

  it('calls onFlush callback after each rAF batch', () => {
    const onFlush = vi.fn();
    const { init, write } = useStreamingParser({ onFlush });
    const container = document.createElement('div');
    init(container);

    write('chunk');
    rafCallbacks.forEach((cb) => cb());

    expect(onFlush).toHaveBeenCalledTimes(1);
  });

  it('destroy finalizes the parser', () => {
    const { init, destroy } = useStreamingParser();
    const container = document.createElement('div');
    init(container);

    destroy();

    expect(mockParserEnd).toHaveBeenCalled();
  });
});
