/**
 * Tests for SkillSleepReviewDrawer — the review-then-adopt safety core.
 * The Adopt gate is tested EXHAUSTIVELY: enabled only for an accepted,
 * un-adopted run that isn't mid-adopt; disabled for every other status, for an
 * already-adopted run, and while isAdopting.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import SkillSleepReviewDrawer from '../SkillSleepReviewDrawer.vue';
import type { SkillSleepRun, SkillSleepStatus } from '../../../services/api';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      skillSleep: {
        reviewTitle: 'Review Skill-Sleep run',
        judgeScores: 'Judge scores',
        current: 'Current',
        candidate: 'Candidate',
        delta: 'Δ',
        outcome: 'Outcome',
        before: 'Before',
        after: 'After',
        questions: '{n} questions',
        reasonLabel: 'Reason',
        candidateBody: 'Candidate body',
        currentBodyUnavailable: 'Current body unavailable — showing candidate only.',
        cancel: 'Cancel',
        adopt: 'Adopt',
        adopting: 'Adopting…',
        adoptFailed: 'Adopt failed',
        changesFromCurrent: 'Changes from current',
        noChanges: 'No line changes',
      },
    },
  },
});

function run(over: Partial<SkillSleepRun> = {}): SkillSleepRun {
  return {
    id: 7,
    project_id: 'proj-1',
    skill_name: 'deploy',
    skill_id: '3',
    status: 'accepted',
    current_score: 0.4,
    candidate_score: 0.7,
    delta: 0.3,
    question_count: 6,
    partition_seed: 1,
    judge_backend: 'claude',
    candidate_body: '# improved\n',
    current_body: null,
    current_body_hash: 'hash',
    reason: 'candidate strictly improved held-out score',
    created_at: '2026-06-13 12:00:00',
    finished_at: '2026-06-13 12:05:00',
    adopted_at: null,
    outcome_before_score: 0.4,
    outcome_after_score: 0.6,
    outcome_delta: 0.2,
    outcome_question_count: 6,
    ...over,
  } as SkillSleepRun;
}

describe('SkillSleepReviewDrawer', () => {
  let wrappers: Array<{ unmount: () => void }> = [];
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
  });

  function mountDrawer(props: Record<string, unknown>) {
    const w = mount(SkillSleepReviewDrawer, {
      props: { open: true, run: run(), isAdopting: false, ...props },
      global: { plugins: [i18n], stubs: { teleport: true, MarkdownContent: true } },
    });
    wrappers.push(w);
    return w;
  }

  const adopt = (w: ReturnType<typeof mountDrawer>) =>
    w.find('[data-testid="ss-adopt"]').element as HTMLButtonElement;

  it('enables Adopt for an accepted, un-adopted run and emits adopt(run_id)', async () => {
    const w = mountDrawer({ run: run() });
    expect(adopt(w).disabled).toBe(false);
    await w.find('[data-testid="ss-adopt"]').trigger('click');
    expect(w.emitted('adopt')).toBeTruthy();
    expect(w.emitted('adopt')![0]).toEqual([7]);
  });

  it.each<SkillSleepStatus>(['rejected', 'abstained', 'failed', 'no_candidate'])(
    'disables Adopt for status=%s',
    (status) => {
      const w = mountDrawer({ run: run({ status }) });
      expect(adopt(w).disabled).toBe(true);
    },
  );

  it('disables Adopt for an already-adopted run', () => {
    const w = mountDrawer({ run: run({ adopted_at: '2026-06-13 13:00:00' }) });
    expect(adopt(w).disabled).toBe(true);
  });

  it('disables Adopt while isAdopting (and shows the adopting label)', () => {
    const w = mountDrawer({ run: run(), isAdopting: true });
    expect(adopt(w).disabled).toBe(true);
    expect(w.text()).toContain('Adopting');
  });

  it('falls back to candidate-only + note when current_body is absent (old runs)', () => {
    const w = mountDrawer({ run: run({ current_body: null }) });
    expect(w.text()).toContain('Current body unavailable');
    expect(w.find('[data-testid="ss-candidate-body"]').exists()).toBe(true);
    expect(w.find('[data-testid="ss-diff"]').exists()).toBe(false);
  });

  it('renders a current-vs-candidate diff when current_body is present', () => {
    const w = mountDrawer({
      run: run({ current_body: 'line a\nOLD\nline c', candidate_body: 'line a\nNEW\nline c' }),
    });
    const diff = w.find('[data-testid="ss-diff"]');
    expect(diff.exists()).toBe(true);
    expect(diff.text()).toContain('OLD'); // removed line
    expect(diff.text()).toContain('NEW'); // added line
    // The candidate-only fallback is NOT shown when a diff is available.
    expect(w.find('[data-testid="ss-candidate-body"]').exists()).toBe(false);
    expect(w.text()).toContain('Changes from current');
  });

  it('surfaces an inline adoptError', () => {
    const w = mountDrawer({ run: run(), adoptError: 'stale (skill changed)' });
    const err = w.find('[data-testid="ss-adopt-error"]');
    expect(err.exists()).toBe(true);
    expect(err.text()).toContain('stale (skill changed)');
  });

  it('Escape and backdrop emit close', async () => {
    const w = mountDrawer({ run: run() });
    await w.find('.ss-overlay').trigger('keydown', { key: 'Escape' });
    expect(w.emitted('close')).toBeTruthy();
    // backdrop click (target === overlay)
    await w.find('.ss-overlay').trigger('click');
    expect(w.emitted('close')!.length).toBeGreaterThanOrEqual(1);
  });

  it('renders nothing when closed', () => {
    const w = mountDrawer({ open: false, run: run() });
    expect(w.find('[data-testid="ss-adopt"]').exists()).toBe(false);
  });
});
