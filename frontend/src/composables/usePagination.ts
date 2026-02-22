import { ref, computed, watch, type Ref, type ComputedRef } from 'vue';

export interface UsePaginationOptions {
  defaultPageSize?: number;
  pageSizeOptions?: number[];
  storageKey?: string;
}

export interface UsePaginationReturn {
  currentPage: Ref<number>;
  pageSize: Ref<number>;
  totalCount: Ref<number>;
  totalPages: ComputedRef<number>;
  offset: ComputedRef<number>;
  isFirstPage: ComputedRef<boolean>;
  isLastPage: ComputedRef<boolean>;
  rangeStart: ComputedRef<number>;
  rangeEnd: ComputedRef<number>;
  pageSizeOptions: number[];
  goToPage: (n: number) => void;
  nextPage: () => void;
  prevPage: () => void;
  resetToFirstPage: () => void;
}

export function usePagination(options: UsePaginationOptions = {}): UsePaginationReturn {
  const {
    defaultPageSize = 25,
    pageSizeOptions = [10, 25, 50],
    storageKey,
  } = options;

  // Restore pageSize from sessionStorage if available
  let initialPageSize = defaultPageSize;
  if (storageKey) {
    try {
      const stored = sessionStorage.getItem(storageKey);
      if (stored) {
        const parsed = parseInt(stored, 10);
        if (!isNaN(parsed) && pageSizeOptions.includes(parsed)) {
          initialPageSize = parsed;
        }
      }
    } catch {
      // Ignore storage errors
    }
  }

  const currentPage = ref(1);
  const pageSize = ref(initialPageSize);
  const totalCount = ref(0);

  const totalPages = computed(() => {
    if (totalCount.value <= 0 || pageSize.value <= 0) return 0;
    return Math.ceil(totalCount.value / pageSize.value);
  });

  const offset = computed(() => (currentPage.value - 1) * pageSize.value);

  const isFirstPage = computed(() => currentPage.value <= 1);
  const isLastPage = computed(() => currentPage.value >= totalPages.value);

  const rangeStart = computed(() => {
    if (totalCount.value === 0) return 0;
    return offset.value + 1;
  });

  const rangeEnd = computed(() => {
    if (totalCount.value === 0) return 0;
    return Math.min(offset.value + pageSize.value, totalCount.value);
  });

  function goToPage(n: number) {
    const clamped = Math.max(1, Math.min(n, totalPages.value || 1));
    currentPage.value = clamped;
  }

  function nextPage() {
    if (!isLastPage.value) {
      currentPage.value++;
    }
  }

  function prevPage() {
    if (!isFirstPage.value) {
      currentPage.value--;
    }
  }

  function resetToFirstPage() {
    currentPage.value = 1;
  }

  // Persist pageSize to sessionStorage on change
  if (storageKey) {
    watch(pageSize, (val) => {
      try {
        sessionStorage.setItem(storageKey, String(val));
      } catch {
        // Ignore storage errors
      }
    });
  }

  // Auto-reset to page 1 when pageSize changes
  watch(pageSize, () => {
    currentPage.value = 1;
  });

  return {
    currentPage,
    pageSize,
    totalCount,
    totalPages,
    offset,
    isFirstPage,
    isLastPage,
    rangeStart,
    rangeEnd,
    pageSizeOptions,
    goToPage,
    nextPage,
    prevPage,
    resetToFirstPage,
  };
}
