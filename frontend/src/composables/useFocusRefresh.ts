import { onMounted, onUnmounted } from 'vue';

export interface UseFocusRefreshOptions {
  /** When true, calls fn once on mount in addition to visibility-change events. */
  immediate?: boolean;
}

/**
 * Re-runs `fn` whenever the document transitions to a visible state
 * (window focus / tab regaining visibility). Use this when a page
 * needs to refresh its data after the user returns from a different
 * tab/window — e.g., kicking off an agent run elsewhere and coming
 * back to see updated memory.
 *
 * The listener is registered on `document.visibilitychange` and
 * removed automatically on unmount.
 */
export function useFocusRefresh(
  fn: () => void | Promise<void>,
  opts: UseFocusRefreshOptions = {},
): void {
  function handler() {
    if (document.visibilityState === 'visible') {
      void fn();
    }
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', handler);
    if (opts.immediate) {
      void fn();
    }
  });

  onUnmounted(() => {
    document.removeEventListener('visibilitychange', handler);
  });
}
