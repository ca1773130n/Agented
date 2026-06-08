/**
 * Toast notification system extracted from App.vue (v0.7.5d).
 *
 * Owns the toasts array, `showToast`, and `dismissToast`. Includes the
 * auto-advance-on-toast logic that drives the tour machine forward when a
 * matching success message arrives. The parent (App.vue) wires `provide`
 * for `showToast` so deeply-nested children retain the existing
 * `inject('showToast')` contract.
 */
import { ref, type Ref } from 'vue';
import type { useTourMachine } from './useTourMachine';
import { TOUR_STEP_MAP } from '../constants/tourSteps';
import { i18n } from '../i18n';

export type ToastType = 'success' | 'error' | 'info' | 'infrastructure';

export interface Toast {
  id: number;
  message: string;
  type: ToastType;
}

type TourMachine = ReturnType<typeof useTourMachine>;

export interface UseToastSystem {
  toasts: Ref<Toast[]>;
  showToast: (message: string, type?: ToastType, duration?: number) => void;
  dismissToast: (id: number) => void;
}

/**
 * Build the toast system. The `tour` argument lets `showToast` auto-advance
 * the tour machine when a success toast matches the current step's
 * `autoAdvanceOnToast` trigger — preserving existing App.vue behavior
 * 1:1.
 */
export function useToastSystem(tour: TourMachine): UseToastSystem {
  const toasts = ref<Toast[]>([]);
  let toastId = 0;

  function showToast(message: string, type: ToastType = 'info', duration?: number) {
    const id = ++toastId;
    const defaultDuration = type === 'infrastructure' ? 8000 : type === 'error' ? 8000 : 4000;
    toasts.value.push({ id, message, type });
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id);
    }, duration ?? defaultDuration);

    // Auto-advance tour when a success toast matches the current step's trigger.
    // Skip auto-advance for backend account steps — the AccountWizard controls advancement.
    if (type === 'success' && tour.isActive.value) {
      const step = tour.currentStep.value;
      const isBackendStep = step.startsWith('backends.');
      if (!isBackendStep) {
        const meta = TOUR_STEP_MAP[step];
        // Match against the LOCALIZED toast text first (resolve the step's
        // i18n key in the active locale) so auto-advance works in ko/ja/zh —
        // the raw English `autoAdvanceOnToast` only matched the en catalog,
        // which silently wedged steps like "monitoring" for non-English
        // operators. Fall back to the English literal for safety.
        const localized = meta?.autoAdvanceI18nKey
          ? (i18n.global.t(meta.autoAdvanceI18nKey) as string)
          : null;
        const matches =
          (localized && message.includes(localized)) ||
          (meta?.autoAdvanceOnToast ? message.includes(meta.autoAdvanceOnToast) : false);
        if (meta && matches) {
          setTimeout(() => tour.nextStep(), 800);
        }
      }
    }
  }

  function dismissToast(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }

  return { toasts, showToast, dismissToast };
}
