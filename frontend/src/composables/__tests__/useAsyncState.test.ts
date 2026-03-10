import { describe, it, expect, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';

// Mock onUnmounted and isAbortError
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

vi.mock('../../services/api', () => ({
  isAbortError: (err: unknown) =>
    err instanceof DOMException && err.name === 'AbortError',
}));

import { useAsyncState } from '../useAsyncState';

describe('useAsyncState', () => {
  it('starts with initial value and not loading', () => {
    const { data, isLoading, error } = useAsyncState(() => Promise.resolve([]), []);
    expect(data.value).toEqual([]);
    expect(isLoading.value).toBe(false);
    expect(error.value).toBeNull();
  });

  it('sets isLoading during execution', async () => {
    let resolve: (val: string) => void;
    const promise = new Promise<string>((r) => { resolve = r; });
    const { isLoading, execute } = useAsyncState(() => promise, '');

    const execPromise = execute();
    expect(isLoading.value).toBe(true);

    resolve!('done');
    await execPromise;
    expect(isLoading.value).toBe(false);
  });

  it('sets data on successful execution', async () => {
    const { data, execute } = useAsyncState(() => Promise.resolve(42), 0);

    await execute();
    expect(data.value).toBe(42);
  });

  it('sets error on failed execution', async () => {
    const { error, isLoading, execute } = useAsyncState(
      () => Promise.reject(new Error('Network failure')),
      null,
    );

    await execute();
    expect(error.value).toBe('Network failure');
    expect(isLoading.value).toBe(false);
  });

  it('handles non-Error rejection', async () => {
    const { error, execute } = useAsyncState(
      () => Promise.reject('string error'),
      null,
    );

    await execute();
    expect(error.value).toBe('string error');
  });

  it('clears error on retry', async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce('ok');

    const { data, error, execute } = useAsyncState(fn, '');

    await execute();
    expect(error.value).toBe('fail');

    await execute();
    expect(error.value).toBeNull();
    expect(data.value).toBe('ok');
  });

  it('cancels previous in-flight request when execute is called again', async () => {
    let callCount = 0;
    const fn = vi.fn().mockImplementation(async () => {
      callCount++;
      const current = callCount;
      await new Promise((r) => setTimeout(r, 10));
      return `result-${current}`;
    });

    const { execute } = useAsyncState(fn, '');

    // Start two requests -- only the second should "win"
    execute();
    await execute();
    await flushPromises();

    // The second call resolves; the first was aborted
    expect(fn).toHaveBeenCalledTimes(2);
  });
});
