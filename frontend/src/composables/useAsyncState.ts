import { ref, type Ref } from 'vue';

export interface UseAsyncStateReturn<T> {
  data: Ref<T>;
  isLoading: Ref<boolean>;
  error: Ref<string | null>;
  execute: () => Promise<void>;
}

/**
 * Generic composable for consistent async state management.
 *
 * Provides a standardized loading/error/data lifecycle for any async operation.
 * Consumers call `execute()` to trigger the async function and the composable
 * manages the `isLoading`, `error`, and `data` refs automatically.
 *
 * @param asyncFn - Async function that returns the data
 * @param initialValue - Initial value for the data ref
 * @returns Object with data, isLoading, error refs and execute function
 *
 * @example
 * ```ts
 * const { data: users, isLoading, error, execute } = useAsyncState(
 *   () => userApi.list(),
 *   []
 * );
 * onMounted(execute);
 * ```
 */
export function useAsyncState<T>(
  asyncFn: () => Promise<T>,
  initialValue: T
): UseAsyncStateReturn<T> {
  const data = ref<T>(initialValue) as Ref<T>;
  const isLoading = ref(false);
  const error = ref<string | null>(null);

  async function execute(): Promise<void> {
    isLoading.value = true;
    error.value = null;
    try {
      data.value = await asyncFn();
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      isLoading.value = false;
    }
  }

  return { data, isLoading, error, execute };
}
