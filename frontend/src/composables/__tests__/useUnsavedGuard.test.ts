import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

// Track registered listeners
let beforeUnloadHandler: ((e: BeforeUnloadEvent) => void) | null = null;
let routeLeaveGuard: (() => boolean | undefined) | null = null;

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return {
    ...actual,
    onMounted: (cb: () => void) => { cb(); }, // execute immediately
    onBeforeUnmount: vi.fn(),
  };
});

vi.mock('vue-router', () => ({
  onBeforeRouteLeave: (guard: () => boolean | undefined) => {
    routeLeaveGuard = guard;
  },
}));

// Spy on addEventListener to capture the beforeunload handler
const origAddEventListener = window.addEventListener.bind(window);
vi.spyOn(window, 'addEventListener').mockImplementation((type: string, handler: unknown) => {
  if (type === 'beforeunload') {
    beforeUnloadHandler = handler as (e: BeforeUnloadEvent) => void;
  }
  return origAddEventListener(type, handler as EventListenerOrEventListenerObject);
});

import { useUnsavedGuard } from '../useUnsavedGuard';

describe('useUnsavedGuard', () => {
  beforeEach(() => {
    beforeUnloadHandler = null;
    routeLeaveGuard = null;
  });

  it('registers beforeunload listener on mount', () => {
    const isDirty = ref(false);
    useUnsavedGuard(isDirty);
    expect(beforeUnloadHandler).not.toBeNull();
  });

  it('registers vue-router beforeRouteLeave guard', () => {
    const isDirty = ref(false);
    useUnsavedGuard(isDirty);
    expect(routeLeaveGuard).not.toBeNull();
  });

  it('beforeunload does nothing when not dirty', () => {
    const isDirty = ref(false);
    useUnsavedGuard(isDirty);

    const event = new Event('beforeunload') as BeforeUnloadEvent;
    const preventDefaultSpy = vi.spyOn(event, 'preventDefault');
    beforeUnloadHandler!(event);

    expect(preventDefaultSpy).not.toHaveBeenCalled();
  });

  it('beforeunload prevents default when dirty', () => {
    const isDirty = ref(true);
    useUnsavedGuard(isDirty);

    const event = new Event('beforeunload') as BeforeUnloadEvent;
    const preventDefaultSpy = vi.spyOn(event, 'preventDefault');
    beforeUnloadHandler!(event);

    expect(preventDefaultSpy).toHaveBeenCalled();
  });

  it('route leave guard returns undefined when not dirty', () => {
    const isDirty = ref(false);
    useUnsavedGuard(isDirty);

    const result = routeLeaveGuard!();
    expect(result).toBeUndefined();
  });

  it('route leave guard calls confirm when dirty', () => {
    // happy-dom may not define window.confirm; ensure it exists for spying
    if (typeof window.confirm !== 'function') {
      window.confirm = () => true;
    }
    const isDirty = ref(true);
    useUnsavedGuard(isDirty);

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const result = routeLeaveGuard!();

    expect(confirmSpy).toHaveBeenCalledWith('You have unsaved changes. Leave anyway?');
    expect(result).toBe(true);
    confirmSpy.mockRestore();
  });
});
