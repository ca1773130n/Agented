import { ref, computed, onMounted, onUnmounted } from 'vue';

const STORAGE_KEY = 'agented-sidebar-collapsed';
const MOBILE_QUERY = '(max-width: 767px)';
const TABLET_QUERY = '(min-width: 768px) and (max-width: 1023px)';

export function useSidebarCollapse() {
  const isCollapsed = ref(sessionStorage.getItem(STORAGE_KEY) === 'true');
  const isMobileOpen = ref(false);
  const isMobileRaw = ref(false);

  let mediaQuery: MediaQueryList | null = null;
  let tabletMediaQuery: MediaQueryList | null = null;

  function handleMediaChange(e: MediaQueryListEvent | MediaQueryList) {
    isMobileRaw.value = e.matches;
    if (!e.matches) {
      // Leaving mobile mode — close mobile overlay
      isMobileOpen.value = false;
    }
  }

  const isMobile = computed(() => isMobileRaw.value);

  function toggleCollapse() {
    if (isMobileRaw.value) return; // no-op on mobile
    isCollapsed.value = !isCollapsed.value;
    sessionStorage.setItem(STORAGE_KEY, String(isCollapsed.value));
  }

  function toggleMobile() {
    isMobileOpen.value = !isMobileOpen.value;
  }

  function closeMobile() {
    isMobileOpen.value = false;
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape' && isMobileOpen.value) {
      isMobileOpen.value = false;
    }
  }

  function handleTabletChange(e: MediaQueryListEvent | MediaQueryList) {
    // Auto-collapse on tablet width if the user hasn't expressed a preference
    // this session. Once they explicitly toggle, sessionStorage holds their
    // choice and we leave it alone.
    if (e.matches && sessionStorage.getItem(STORAGE_KEY) === null) {
      isCollapsed.value = true;
    }
  }

  onMounted(() => {
    mediaQuery = window.matchMedia(MOBILE_QUERY);
    isMobileRaw.value = mediaQuery.matches;
    mediaQuery.addEventListener('change', handleMediaChange);

    tabletMediaQuery = window.matchMedia(TABLET_QUERY);
    handleTabletChange(tabletMediaQuery);
    tabletMediaQuery.addEventListener('change', handleTabletChange);

    document.addEventListener('keydown', handleKeydown);
  });

  onUnmounted(() => {
    if (mediaQuery) {
      mediaQuery.removeEventListener('change', handleMediaChange);
    }
    if (tabletMediaQuery) {
      tabletMediaQuery.removeEventListener('change', handleTabletChange);
    }
    document.removeEventListener('keydown', handleKeydown);
  });

  return {
    isCollapsed,
    isMobileOpen,
    isMobile,
    toggleCollapse,
    toggleMobile,
    closeMobile,
    handleKeydown,
  };
}
