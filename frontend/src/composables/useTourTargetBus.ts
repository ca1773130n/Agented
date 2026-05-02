/**
 * Selector-driven element resolver for the tour overlay.
 *
 * The previous TourOverlay held a `targetEl: ref<HTMLElement | null>` that
 * was stale across route-param changes — when the slot remounted, the
 * cached element was unconnected and the overlay couldn't recover without
 * a parent-side hack (EntityLayout's `keepStale`, wave 6).
 *
 * Subscribers register a CSS selector and a callback. The bus:
 *   - resolves immediately on subscribe (synchronous initial call)
 *   - watches the active route's main container (`#main-content`, the
 *     `<main>` element wrapping `<router-view>`) for childList/subtree
 *     changes via a MutationObserver per subscriber, and re-emits when
 *     the matched element changes (mount, unmount, replacement). Falls
 *     back to `document.body` when `#main-content` isn't mounted yet
 *     (e.g. on the welcome screen, which uses a separate layout).
 *
 * The scoping satisfies OB-41: "scoped to the route's root element,
 * not document.body". Header/sidebar churn outside the main container
 * no longer triggers re-resolution.
 *
 * Multiple subscribers on the same selector each get their own observer
 * and callback. Unsubscribe disconnects the observer.
 */

export type TourTargetCallback = (element: HTMLElement | null) => void;

export interface TourTargetBus {
  subscribe(selector: string, cb: TourTargetCallback): () => void;
}

export function useTourTargetBus(): TourTargetBus {
  function subscribe(selector: string, cb: TourTargetCallback): () => void {
    let last: HTMLElement | null = null;

    const resolve = () => {
      const next = (document.querySelector(selector) as HTMLElement | null) ?? null;
      if (next !== last) {
        last = next;
        cb(next);
      }
    };

    // Synchronous first call — even if it resolves to null.
    last = (document.querySelector(selector) as HTMLElement | null) ?? null;
    cb(last);

    // OB-41: scope to the route's main container, fall back to body
    // when not yet mounted (welcome screen layout).
    const scopeRoot =
      (document.querySelector('#main-content') as HTMLElement | null) ??
      document.body;
    const observer = new MutationObserver(resolve);
    observer.observe(scopeRoot, { childList: true, subtree: true });

    return () => observer.disconnect();
  }

  return { subscribe };
}
