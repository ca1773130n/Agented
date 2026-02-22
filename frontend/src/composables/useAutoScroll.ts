import { ref, onMounted, onUnmounted, type Ref } from 'vue';

/**
 * Smart auto-scrolling composable based on Agent Zero's scroller.js pattern.
 * Uses a ResizeObserver on the container's first child to detect content
 * height changes, and only auto-scrolls when the user is already at the bottom.
 * Preserves scroll position when user has scrolled up.
 */
export function useAutoScroll(containerRef: Ref<HTMLElement | null>) {
  const TOLERANCE_PX = 32; // ~2rem tolerance for bottom detection
  const isAtBottom = ref(true);

  let resizeObserver: ResizeObserver | null = null;

  function checkBottom() {
    const el = containerRef.value;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    isAtBottom.value = distanceFromBottom <= TOLERANCE_PX;
  }

  function scrollToBottom(smooth = true) {
    const el = containerRef.value;
    if (!el) return;
    if (isAtBottom.value) {
      el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'instant' });
    }
  }

  function onContentResize() {
    if (isAtBottom.value) {
      scrollToBottom(false); // Instant scroll during rapid updates
    }
  }

  function forceScrollToBottom() {
    isAtBottom.value = true;
    const el = containerRef.value;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
  }

  function onScroll() {
    checkBottom();
  }

  onMounted(() => {
    const el = containerRef.value;
    if (!el) return;

    el.addEventListener('scroll', onScroll, { passive: true });

    resizeObserver = new ResizeObserver(onContentResize);
    if (el.firstElementChild) {
      resizeObserver.observe(el.firstElementChild);
    }
  });

  onUnmounted(() => {
    const el = containerRef.value;
    if (el) {
      el.removeEventListener('scroll', onScroll);
    }
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver = null;
    }
  });

  return {
    isAtBottom,
    scrollToBottom,
    forceScrollToBottom,
  };
}
