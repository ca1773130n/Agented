import { ref, watch, type Ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

/**
 * A tab ref synced to a URL query param — so the active tab is deep-linkable,
 * survives a refresh, and works with the browser back/forward buttons. Mirrors
 * the ?tab= behavior of components/base/TabbedViewHost.vue for pages/components
 * that manage their tab state manually.
 *
 * Usage: `const activeTab = useUrlTab(['list', 'diff'] as const, 'list');`
 * Writing to the returned ref (e.g. `@click="activeTab = 'diff'"`) updates the URL.
 */
export function useUrlTab<T extends string>(
  valid: readonly T[],
  fallback: T,
  paramName = 'tab',
): Ref<T> {
  const route = useRoute();
  const router = useRouter();
  const normalize = (v: unknown): T =>
    (valid as readonly string[]).includes(v as string) ? (v as T) : fallback;

  const tab = ref(normalize(route.query[paramName])) as Ref<T>;

  // ref -> URL (replace, so tab switches don't spam history)
  watch(tab, (next) => {
    if (route.query[paramName] !== next) {
      router.replace({ query: { ...route.query, [paramName]: next } });
    }
  });
  // URL -> ref (back/forward, external navigation, deep-link landing)
  watch(
    () => route.query[paramName],
    (q) => {
      const n = normalize(q);
      if (n !== tab.value) tab.value = n;
    },
  );

  return tab;
}
