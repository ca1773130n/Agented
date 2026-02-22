import { type Ref, watchEffect, onUnmounted } from 'vue';

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Traps keyboard focus inside a container element while `isActive` is true.
 *
 * - Tab on last focusable element wraps to first
 * - Shift+Tab on first focusable element wraps to last
 * - On activate: focuses the container so @keydown.escape works
 * - On deactivate: restores focus to the previously-focused element
 */
export function useFocusTrap(
  containerRef: Ref<HTMLElement | null>,
  isActive: Ref<boolean>,
): void {
  let previouslyFocused: Element | null = null;

  function handleKeydown(e: KeyboardEvent) {
    if (e.key !== 'Tab') return;

    const container = containerRef.value;
    if (!container) return;

    const focusable = Array.from(
      container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
    ).filter((el) => el.offsetParent !== null); // exclude hidden elements

    if (focusable.length === 0) {
      e.preventDefault();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first || document.activeElement === container) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  function activate() {
    previouslyFocused = document.activeElement;
    const container = containerRef.value;
    if (container) {
      container.addEventListener('keydown', handleKeydown);
      // Focus the container itself so @keydown.escape triggers
      container.focus();
    }
  }

  function deactivate() {
    const container = containerRef.value;
    if (container) {
      container.removeEventListener('keydown', handleKeydown);
    }
    if (previouslyFocused && previouslyFocused instanceof HTMLElement) {
      previouslyFocused.focus();
    }
    previouslyFocused = null;
  }

  watchEffect((onCleanup) => {
    if (isActive.value && containerRef.value) {
      activate();
      onCleanup(() => deactivate());
    }
  });

  onUnmounted(() => {
    deactivate();
  });
}
