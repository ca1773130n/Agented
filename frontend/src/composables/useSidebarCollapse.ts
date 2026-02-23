import { ref, computed, onMounted, onUnmounted } from 'vue';

const STORAGE_KEY = 'agented-sidebar-collapsed';
const MOBILE_QUERY = '(max-width: 767px)';

export function useSidebarCollapse() {
  const isCollapsed = ref(sessionStorage.getItem(STORAGE_KEY) === 'true');
  const isMobileOpen = ref(false);
  const isMobileRaw = ref(false);

  let mediaQuery: MediaQueryList | null = null;

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

  onMounted(() => {
    mediaQuery = window.matchMedia(MOBILE_QUERY);
    isMobileRaw.value = mediaQuery.matches;
    mediaQuery.addEventListener('change', handleMediaChange);
  });

  onUnmounted(() => {
    if (mediaQuery) {
      mediaQuery.removeEventListener('change', handleMediaChange);
    }
  });

  return {
    isCollapsed,
    isMobileOpen,
    isMobile,
    toggleCollapse,
    toggleMobile,
    closeMobile,
  };
}
