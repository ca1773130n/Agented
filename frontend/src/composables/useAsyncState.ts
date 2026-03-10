import { ref, onUnmounted, type Ref } from 'vue';
import { isAbortError } from '../services/api';

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
 * Pending requests are automatically cancelled on component unmount via
 * AbortController. Aborted requests are silently ignored (no error state).
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

  // AbortController for cancelling pending requests on unmount
  let abortController = new AbortController();

  async function execute(): Promise<void> {
    // Cancel any in-flight request before starting a new one
    abortController.abort();
    abortController = new AbortController();
    const { signal } = abortController;

    isLoading.value = true;
    error.value = null;
    try {
      const result = await asyncFn();
      if (signal.aborted) return;
      data.value = result;
    } catch (err: unknown) {
      if (isAbortError(err) || abortController.signal.aborted) return;
      error.value = err instanceof Error ? err.message : String(err);
    } finally {
      if (!abortController.signal.aborted) {
        isLoading.value = false;
      }
    }
  }

  onUnmounted(() => {
    abortController.abort();
  });

  return { data, isLoading, error, execute };
}
