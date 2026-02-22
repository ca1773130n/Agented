import { onMounted, onBeforeUnmount, type Ref } from 'vue';
import { onBeforeRouteLeave } from 'vue-router';

/**
 * Composable that protects against unsaved changes being lost.
 *
 * Provides two layers of protection:
 * 1. `onBeforeRouteLeave` — intercepts in-app navigation via Vue Router
 *    and shows a confirm dialog when the form has unsaved changes.
 * 2. `beforeunload` — intercepts page reload/tab close and shows the
 *    browser's native "Leave site?" dialog.
 *
 * Must be called during component setup (in <script setup>).
 */
export function useUnsavedGuard(isDirty: Ref<boolean>) {
  // In-app navigation guard (Vue Router)
  onBeforeRouteLeave(() => {
    if (isDirty.value) {
      return window.confirm('You have unsaved changes. Leave anyway?');
    }
  });

  // Page reload / tab close guard (browser native)
  function onBeforeUnload(event: BeforeUnloadEvent) {
    if (isDirty.value) {
      event.preventDefault();
      event.returnValue = '';
    }
  }

  onMounted(() => {
    window.addEventListener('beforeunload', onBeforeUnload);
  });

  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', onBeforeUnload);
  });
}
