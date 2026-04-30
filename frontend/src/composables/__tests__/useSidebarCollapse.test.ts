import { describe, it, expect, vi, beforeEach } from 'vitest';

// Capture lifecycle callbacks
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

import { useSidebarCollapse } from '../useSidebarCollapse';

describe('useSidebarCollapse', () => {
  beforeEach(() => {
    mountedCallbacks.length = 0;
    unmountedCallbacks.length = 0;
    sessionStorage.clear();
  });

  it('starts not collapsed by default', () => {
    const { isCollapsed } = useSidebarCollapse();
    expect(isCollapsed.value).toBe(false);
  });

  it('restores collapsed state from sessionStorage', () => {
    sessionStorage.setItem('agented-sidebar-collapsed', 'true');
    const { isCollapsed } = useSidebarCollapse();
    expect(isCollapsed.value).toBe(true);
  });

  it('toggleCollapse flips isCollapsed and persists', () => {
    const { isCollapsed, toggleCollapse } = useSidebarCollapse();
    expect(isCollapsed.value).toBe(false);

    toggleCollapse();
    expect(isCollapsed.value).toBe(true);
    expect(sessionStorage.getItem('agented-sidebar-collapsed')).toBe('true');

    toggleCollapse();
    expect(isCollapsed.value).toBe(false);
    expect(sessionStorage.getItem('agented-sidebar-collapsed')).toBe('false');
  });

  it('toggleMobile flips isMobileOpen', () => {
    const { isMobileOpen, toggleMobile } = useSidebarCollapse();
    expect(isMobileOpen.value).toBe(false);

    toggleMobile();
    expect(isMobileOpen.value).toBe(true);

    toggleMobile();
    expect(isMobileOpen.value).toBe(false);
  });

  it('closeMobile sets isMobileOpen to false', () => {
    const { isMobileOpen, toggleMobile, closeMobile } = useSidebarCollapse();

    toggleMobile();
    expect(isMobileOpen.value).toBe(true);

    closeMobile();
    expect(isMobileOpen.value).toBe(false);
  });

  it('isMobile is initially false', () => {
    const { isMobile } = useSidebarCollapse();
    expect(isMobile.value).toBe(false);
  });

  describe('tablet auto-collapse', () => {
    function makeMql(matches: boolean) {
      const listeners = new Set<(e: MediaQueryListEvent) => void>();
      const mql = {
        matches,
        media: '',
        addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.add(cb),
        removeEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb),
        dispatchEvent: () => true,
        onchange: null,
      };
      return { mql, listeners };
    }

    it('auto-collapses when entering the tablet range with no stored preference', () => {
      const tablet = makeMql(true);
      const mobile = makeMql(false);
      vi.stubGlobal('matchMedia', (q: string) =>
        q.includes('max-width: 1023px') ? tablet.mql : mobile.mql,
      );

      const { isCollapsed } = useSidebarCollapse();
      mountedCallbacks.forEach((cb) => cb());

      expect(isCollapsed.value).toBe(true);
      vi.unstubAllGlobals();
    });

    it('respects an explicit non-collapsed sessionStorage preference', () => {
      sessionStorage.setItem('agented-sidebar-collapsed', 'false');
      const tablet = makeMql(true);
      const mobile = makeMql(false);
      vi.stubGlobal('matchMedia', (q: string) =>
        q.includes('max-width: 1023px') ? tablet.mql : mobile.mql,
      );

      const { isCollapsed } = useSidebarCollapse();
      mountedCallbacks.forEach((cb) => cb());

      expect(isCollapsed.value).toBe(false);
      vi.unstubAllGlobals();
    });
  });

  describe('keyboard nav', () => {
    it('Escape closes the mobile overlay when open', () => {
      const { isMobileOpen, toggleMobile, handleKeydown } = useSidebarCollapse();
      toggleMobile();
      expect(isMobileOpen.value).toBe(true);

      handleKeydown(new KeyboardEvent('keydown', { key: 'Escape' }));
      expect(isMobileOpen.value).toBe(false);
    });

    it('Escape is a no-op when the mobile overlay is closed', () => {
      const { isMobileOpen, handleKeydown } = useSidebarCollapse();
      expect(isMobileOpen.value).toBe(false);

      handleKeydown(new KeyboardEvent('keydown', { key: 'Escape' }));
      expect(isMobileOpen.value).toBe(false);
    });

    it('non-Escape keys are ignored', () => {
      const { isMobileOpen, toggleMobile, handleKeydown } = useSidebarCollapse();
      toggleMobile();

      handleKeydown(new KeyboardEvent('keydown', { key: 'Enter' }));
      expect(isMobileOpen.value).toBe(true);
    });
  });
});
