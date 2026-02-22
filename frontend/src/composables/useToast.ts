import { inject } from 'vue';

export type ToastType = 'success' | 'error' | 'info' | 'infrastructure';

export type ShowToastFn = (message: string, type: ToastType, duration?: number) => void;

/**
 * Provides access to the app-level toast notification function.
 * Replaces direct inject('showToast') calls with proper typing.
 */
export function useToast(): ShowToastFn {
  const showToast = inject<ShowToastFn>('showToast');
  if (!showToast) {
    throw new Error('useToast() requires showToast to be provided by a parent component');
  }
  return showToast;
}
