/**
 * v0.7.6: Codex follow-up coverage for useToastSystem.
 *
 * Pre-existing App.test.ts only mounted the parent and asserted toast
 * container existence — it never exercised the auto-advance branch nor
 * the `backends.*` skip guard. These tests cover both, plus the basic
 * show/dismiss/auto-expire behavior.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { computed, ref, type ComputedRef, type Ref } from 'vue';
import { useToastSystem } from '../useToastSystem';
import { i18n } from '../../i18n';

// Build a minimal tour-machine fake matching the shape useToastSystem reads.
// We only need `isActive` (boolean ref) and `currentStep` (string ref) plus
// a `nextStep` spy. The rest of the surface is unused.
interface FakeTour {
  isActive: ComputedRef<boolean> | Ref<boolean>;
  currentStep: ComputedRef<string> | Ref<string>;
  nextStep: ReturnType<typeof vi.fn>;
}

function makeTour(opts: { active: boolean; step: string }): FakeTour {
  const active = ref(opts.active);
  const step = ref(opts.step);
  return {
    isActive: computed(() => active.value),
    currentStep: computed(() => step.value),
    nextStep: vi.fn(),
  };
}

describe('useToastSystem', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  it('showToast adds an entry to the toasts array', () => {
    const tour = makeTour({ active: false, step: 'idle' });
    // Cast to any: the fake tour intentionally omits unused TourMachine surface.
    const { toasts, showToast } = useToastSystem(tour as never);

    showToast('Hello', 'info');
    expect(toasts.value).toHaveLength(1);
    expect(toasts.value[0].message).toBe('Hello');
    expect(toasts.value[0].type).toBe('info');
    expect(typeof toasts.value[0].id).toBe('number');
  });

  it('dismissToast removes by id', () => {
    const tour = makeTour({ active: false, step: 'idle' });
    const { toasts, showToast, dismissToast } = useToastSystem(tour as never);

    showToast('A', 'info');
    showToast('B', 'info');
    expect(toasts.value).toHaveLength(2);
    const firstId = toasts.value[0].id;
    dismissToast(firstId);
    expect(toasts.value).toHaveLength(1);
    expect(toasts.value[0].message).toBe('B');
  });

  it('auto-dismisses after the default duration (4000ms for info)', () => {
    const tour = makeTour({ active: false, step: 'idle' });
    const { toasts, showToast } = useToastSystem(tour as never);

    showToast('Vanish', 'info');
    expect(toasts.value).toHaveLength(1);
    vi.advanceTimersByTime(3999);
    expect(toasts.value).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(toasts.value).toHaveLength(0);
  });

  it('auto-dismisses error toasts after 8000ms', () => {
    const tour = makeTour({ active: false, step: 'idle' });
    const { toasts, showToast } = useToastSystem(tour as never);

    showToast('Boom', 'error');
    vi.advanceTimersByTime(7999);
    expect(toasts.value).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(toasts.value).toHaveLength(0);
  });

  it('honors a caller-supplied duration override', () => {
    const tour = makeTour({ active: false, step: 'idle' });
    const { toasts, showToast } = useToastSystem(tour as never);

    showToast('Quick', 'info', 200);
    vi.advanceTimersByTime(199);
    expect(toasts.value).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(toasts.value).toHaveLength(0);
  });

  // -- Tour auto-advance branch coverage ---------------------------------

  it('does NOT call tour.nextStep when current step is in backends.* (Codex skip guard)', () => {
    const tour = makeTour({ active: true, step: 'backends.claude' });
    const { showToast } = useToastSystem(tour as never);

    // Even if the message would have matched a step trigger, backends.* is
    // owned by AccountWizard — auto-advance must not fire here.
    showToast('Account saved', 'success');
    vi.advanceTimersByTime(2000);
    expect(tour.nextStep).not.toHaveBeenCalled();
  });

  it('calls tour.nextStep ~800ms after a matching success toast on a non-backend step', () => {
    // workspace step has autoAdvanceOnToast: 'Workspace root saved'
    const tour = makeTour({ active: true, step: 'workspace' });
    const { showToast } = useToastSystem(tour as never);

    showToast('Workspace root saved', 'success');
    expect(tour.nextStep).not.toHaveBeenCalled();
    // setTimeout(..., 800) inside showToast.
    vi.advanceTimersByTime(799);
    expect(tour.nextStep).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(tour.nextStep).toHaveBeenCalledTimes(1);
  });

  it('does NOT double-advance when the step already moved before the 800ms timer fires', () => {
    // Mirrors saveWorkspaceRoot: the success toast arms the 800ms auto-advance
    // timer, then the caller advances explicitly (workspace → backends.claude).
    // When the timer fires the step has already moved, so it must NOT advance
    // again — the old behavior double-advanced and skipped the Claude Code
    // account step (landing on Codex).
    const active = ref(true);
    const step = ref('workspace');
    const nextStep = vi.fn();
    const tour = {
      isActive: computed(() => active.value),
      currentStep: computed(() => step.value),
      nextStep,
    };
    const { showToast } = useToastSystem(tour as never);

    showToast('Workspace root saved', 'success');
    // Caller advances explicitly right after the toast, before the 800ms timer.
    step.value = 'backends.claude';
    vi.advanceTimersByTime(800);
    expect(nextStep).not.toHaveBeenCalled();
  });

  it('does NOT auto-advance when tour is inactive', () => {
    const tour = makeTour({ active: false, step: 'workspace' });
    const { showToast } = useToastSystem(tour as never);

    showToast('Workspace root saved', 'success');
    vi.advanceTimersByTime(2000);
    expect(tour.nextStep).not.toHaveBeenCalled();
  });

  it('does NOT auto-advance when toast type is not success', () => {
    const tour = makeTour({ active: true, step: 'workspace' });
    const { showToast } = useToastSystem(tour as never);

    showToast('Workspace root saved', 'info');
    vi.advanceTimersByTime(2000);
    expect(tour.nextStep).not.toHaveBeenCalled();
  });

  it('does NOT auto-advance when message does not include the step trigger', () => {
    const tour = makeTour({ active: true, step: 'workspace' });
    const { showToast } = useToastSystem(tour as never);

    showToast('Something else happened', 'success');
    vi.advanceTimersByTime(2000);
    expect(tour.nextStep).not.toHaveBeenCalled();
  });

  // -- Locale-independent auto-advance (the monitoring/ko regression) -------

  it('auto-advances on a NON-English toast by resolving the step i18n key', () => {
    // Simulate a non-English operator: register a fake locale whose
    // monitoring-saved toast is a distinctive non-English string, switch to
    // it, and fire that exact toast on the monitoring step. The old code
    // matched only the English literal 'Monitoring settings saved' and so
    // never advanced in ko/ja/zh — wedging the step.
    const prev = (i18n.global.locale as unknown as { value: string }).value;
    i18n.global.setLocaleMessage('xx-test', {
      settings: { general: { toastMonitoringSaved: '모니터링-설정-저장됨-UNIQUE' } },
    } as never);
    (i18n.global.locale as unknown as { value: string }).value = 'xx-test';
    try {
      const tour = makeTour({ active: true, step: 'monitoring' });
      const { showToast } = useToastSystem(tour as never);

      showToast('모니터링-설정-저장됨-UNIQUE', 'success');
      expect(tour.nextStep).not.toHaveBeenCalled();
      vi.advanceTimersByTime(800);
      expect(tour.nextStep).toHaveBeenCalledTimes(1);
    } finally {
      (i18n.global.locale as unknown as { value: string }).value = prev;
    }
  });
});
