import { ref, onMounted, type Ref } from 'vue';
import {
  useListFilter,
  type UseListFilterOptions,
  type UseListFilterReturn,
} from './useListFilter';
import { usePagination, type UsePaginationOptions, type UsePaginationReturn } from './usePagination';

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

  async function load(): Promise<void> {
    isLoading.value = true;
    loadError.value = null;
    try {
      const result = await loadFn();
      items.value = result.items;
      pagination.totalCount.value = result.total ?? result.items.length;
    } catch (err: unknown) {
      loadError.value = err instanceof Error ? err.message : String(err);
    } finally {
      isLoading.value = false;
    }
  }

  if (loadOnMount !== false) {
    onMounted(() => load());
  }

  return {
    ...filter,
    items,
    isLoading,
    loadError,
    load,
    pagination,
  };
}
