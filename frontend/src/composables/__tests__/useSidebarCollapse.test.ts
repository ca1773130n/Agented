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
});
