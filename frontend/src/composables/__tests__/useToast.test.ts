import { describe, it, expect, vi, beforeEach } from 'vitest';

// vi.mock is hoisted -- cannot reference top-level variables in the factory.
// Instead, mock 'vue' to return the real module and spy on inject after import.

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return {
    ...actual,
    inject: vi.fn(),
  };
});

import { inject } from 'vue';
import { useToast } from '../useToast';

const mockInject = inject as ReturnType<typeof vi.fn>;

describe('useToast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns the injected showToast function', () => {
    const fakeFn = vi.fn();
    mockInject.mockReturnValue(fakeFn);

    const showToast = useToast();
    expect(showToast).toBe(fakeFn);
  });

  it('throws when showToast is not provided', () => {
    mockInject.mockReturnValue(undefined);

    expect(() => useToast()).toThrow(
      'useToast() requires showToast to be provided by a parent component',
    );
  });

  it('calls inject with the correct key', () => {
    mockInject.mockReturnValue(vi.fn());
    useToast();
    expect(mockInject).toHaveBeenCalledWith('showToast');
  });
});
