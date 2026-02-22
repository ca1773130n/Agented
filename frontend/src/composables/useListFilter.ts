import { ref, computed, watchEffect, type Ref, type ComputedRef } from 'vue';

export interface UseListFilterOptions<T> {
  items: Ref<T[]>;
  searchFields: (keyof T)[];
  defaultSort?: { field: string; order: 'asc' | 'desc' };
  storageKey?: string;
  sortAccessors?: Record<string, (item: T) => string | number | undefined>;
}

export interface UseListFilterReturn<T> {
  searchQuery: Ref<string>;
  sortField: Ref<string>;
  sortOrder: Ref<'asc' | 'desc'>;
  filteredAndSorted: ComputedRef<T[]>;
  hasActiveFilter: ComputedRef<boolean>;
  resultCount: ComputedRef<number>;
  totalCount: ComputedRef<number>;
}

export function useListFilter<T>(options: UseListFilterOptions<T>): UseListFilterReturn<T> {
  const { items, searchFields, defaultSort, storageKey, sortAccessors } = options;

  // Restore from sessionStorage if available
  let initialSearch = '';
  let initialSortField = defaultSort?.field ?? 'name';
  let initialSortOrder: 'asc' | 'desc' = defaultSort?.order ?? 'asc';

  if (storageKey) {
    try {
      const stored = sessionStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (typeof parsed.searchQuery === 'string') initialSearch = parsed.searchQuery;
        if (typeof parsed.sortField === 'string') initialSortField = parsed.sortField;
        if (parsed.sortOrder === 'asc' || parsed.sortOrder === 'desc') initialSortOrder = parsed.sortOrder;
      }
    } catch {
      // Ignore parse errors
    }
  }

  const searchQuery = ref(initialSearch);
  const sortField = ref(initialSortField);
  const sortOrder = ref<'asc' | 'desc'>(initialSortOrder);

  // Persist to sessionStorage on change
  if (storageKey) {
    watchEffect(() => {
      try {
        sessionStorage.setItem(
          storageKey,
          JSON.stringify({
            searchQuery: searchQuery.value,
            sortField: sortField.value,
            sortOrder: sortOrder.value,
          }),
        );
      } catch {
        // Ignore storage errors
      }
    });
  }

  const filteredAndSorted = computed(() => {
    let result = items.value;

    // Filter by search query
    const q = searchQuery.value.toLowerCase().trim();
    if (q) {
      result = result.filter((item) => {
        return searchFields.some((field) => {
          const val = item[field];
          const str = val == null ? '' : String(val);
          return str.toLowerCase().includes(q);
        });
      });
    }

    // Sort
    const field = sortField.value;
    const order = sortOrder.value;
    const accessor = sortAccessors?.[field];

    result = [...result].sort((a, b) => {
      let aVal: string | number | undefined;
      let bVal: string | number | undefined;

      if (accessor) {
        aVal = accessor(a);
        bVal = accessor(b);
      } else {
        aVal = (a as Record<string, unknown>)[field] as string | number | undefined;
        bVal = (b as Record<string, unknown>)[field] as string | number | undefined;
      }

      // Handle nullish values
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;

      let cmp: number;
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        cmp = aVal.localeCompare(bVal, undefined, { sensitivity: 'base' });
      } else {
        cmp = Number(aVal) - Number(bVal);
      }

      return order === 'asc' ? cmp : -cmp;
    });

    return result;
  });

  const hasActiveFilter = computed(() => searchQuery.value.trim().length > 0);
  const resultCount = computed(() => filteredAndSorted.value.length);
  const totalCount = computed(() => items.value.length);

  return {
    searchQuery,
    sortField,
    sortOrder,
    filteredAndSorted,
    hasActiveFilter,
    resultCount,
    totalCount,
  };
}
