import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

// Mock Vue lifecycle hooks so we can call outside a component
const mountedCallbacks: (() => void)[] = [];
const unmountedCallbacks: (() => void)[] = [];

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return {
    ...actual,
    onMounted: (cb: () => void) => { mountedCallbacks.push(cb); },
    onUnmounted: (cb: () => void) => { unmountedCallbacks.push(cb); },
  };
});

import { useAutoScroll } from '../useAutoScroll';

function createMockElement(overrides: Partial<HTMLElement> = {}) {
  const el = document.createElement('div');
  Object.defineProperty(el, 'scrollHeight', { value: overrides.scrollHeight ?? 1000, configurable: true });
  Object.defineProperty(el, 'scrollTop', { value: overrides.scrollTop ?? 0, writable: true, configurable: true });
  Object.defineProperty(el, 'clientHeight', { value: overrides.clientHeight ?? 500, configurable: true });
  el.scrollTo = vi.fn();
  return el;
}

describe('useAutoScroll', () => {
  beforeEach(() => {
    mountedCallbacks.length = 0;
    unmountedCallbacks.length = 0;
  });

  it('starts with isAtBottom = true', () => {
    const containerRef = ref<HTMLElement | null>(null);
    const { isAtBottom } = useAutoScroll(containerRef);
    expect(isAtBottom.value).toBe(true);
  });

  it('scrollToBottom calls el.scrollTo when isAtBottom is true', () => {
    const el = createMockElement({ scrollHeight: 1000, scrollTop: 500, clientHeight: 500 });
    const containerRef = ref<HTMLElement | null>(el);
    const { scrollToBottom } = useAutoScroll(containerRef);

    scrollToBottom();
    expect(el.scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: 'smooth' });
  });

  it('scrollToBottom does not scroll when isAtBottom is false', () => {
    const el = createMockElement({ scrollHeight: 1000, scrollTop: 0, clientHeight: 500 });
    const containerRef = ref<HTMLElement | null>(el);
    const { scrollToBottom, isAtBottom } = useAutoScroll(containerRef);

    // Manually set isAtBottom to false (simulating user scrolled up)
    isAtBottom.value = false;

    scrollToBottom();
    expect(el.scrollTo).not.toHaveBeenCalled();
  });

  it('forceScrollToBottom scrolls regardless of isAtBottom', () => {
    const el = createMockElement({ scrollHeight: 2000 });
    const containerRef = ref<HTMLElement | null>(el);
    const { forceScrollToBottom, isAtBottom } = useAutoScroll(containerRef);

    isAtBottom.value = false;
    forceScrollToBottom();

    expect(isAtBottom.value).toBe(true);
    expect(el.scrollTo).toHaveBeenCalledWith({ top: 2000, behavior: 'instant' });
  });

  it('scrollToBottom with smooth=false uses instant behavior', () => {
    const el = createMockElement({ scrollHeight: 500 });
    const containerRef = ref<HTMLElement | null>(el);
    const { scrollToBottom } = useAutoScroll(containerRef);

    scrollToBottom(false);
    expect(el.scrollTo).toHaveBeenCalledWith({ top: 500, behavior: 'instant' });
  });
});
