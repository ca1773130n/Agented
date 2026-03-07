import { ref, onMounted, onUnmounted, type Ref } from 'vue';
import {
  useListFilter,
  type UseListFilterOptions,
  type UseListFilterReturn,
} from './useListFilter';
import { usePagination, type UsePaginationOptions, type UsePaginationReturn } from './usePagination';
import { isAbortError } from '../services/api';

export interface UseDataPageOptions<T> {
  loadFn: () => Promise<{ items: T[]; total?: number }>;
  filterOptions: Omit<UseListFilterOptions<T>, 'items'>;
  paginationOptions?: UsePaginationOptions;
  loadOnMount?: boolean;
}

export interface UseDataPageReturn<T> extends UseListFilterReturn<T> {
  items: Ref<T[]>;
  isLoading: Ref<boolean>;
  loadError: Ref<string | null>;
  load: () => Promise<void>;
  pagination: UsePaginationReturn;
}

export function useDataPage<T>(options: UseDataPageOptions<T>): UseDataPageReturn<T> {
  const { loadFn, filterOptions, paginationOptions, loadOnMount } = options;

  const items = ref<T[]>([]) as Ref<T[]>;
  const isLoading = ref(true);
  const loadError = ref<string | null>(null);

  const filter = useListFilter<T>({ items, ...filterOptions });
  const pagination = usePagination(paginationOptions);

  // AbortController for cancelling pending requests on unmount
  let abortController = new AbortController();

  async function load(): Promise<void> {
    // Cancel any in-flight request before starting a new one
    abortController.abort();
    abortController = new AbortController();
    const { signal } = abortController;

    isLoading.value = true;
    loadError.value = null;
    try {
      const result = await loadFn();
      if (signal.aborted) return; // Component unmounted during fetch
      items.value = result.items;
      pagination.totalCount.value = result.total ?? result.items.length;
    } catch (err: unknown) {
      if (isAbortError(err) || abortController.signal.aborted) return;
      loadError.value = err instanceof Error ? err.message : String(err);
    } finally {
      if (!abortController.signal.aborted) {
        isLoading.value = false;
      }
    }
  }

  if (loadOnMount !== false) {
    onMounted(() => load());
  }

  onUnmounted(() => {
    abortController.abort();
  });

  return {
    ...filter,
    items,
    isLoading,
    loadError,
    load,
    pagination,
  };
}
