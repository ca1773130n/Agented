/**
 * Route-aware layout state extracted from App.vue (v0.7.5d).
 *
 * Computes `isWelcomePage` (welcome page is rendered fullscreen, outside
 * the main shell) and `isFullBleed` (route opts out of content padding).
 */
import { computed, type ComputedRef } from 'vue';
import { useRoute } from 'vue-router';

export interface UseAppLayout {
  isWelcomePage: ComputedRef<boolean>;
  isFullBleed: ComputedRef<boolean>;
}

export function useAppLayout(): UseAppLayout {
  const route = useRoute();
  const isFullBleed = computed(() => route.meta.fullBleed === true);
  const isWelcomePage = computed(() => route.name === 'welcome');
  return { isWelcomePage, isFullBleed };
}
