/**
 * Tests for SkillSleepCard:
 *   - one row per run with mapped verdict badge + judge/outcome deltas
 *   - accepted+un-adopted → Review button that emits open-run
 *   - adopted run → Adopted badge, no Review
 *   - empty list → EmptyState; api rejection → error branch
 *   - reload() re-fetches
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import SkillSleepCard from '../SkillSleepCard.vue';

vi.mock('../../../../services/api', () => ({
  skillSleepApi: { listRuns: vi.fn() },
  ApiError: class ApiError extends Error {},
}));

import { skillSleepApi } from '../../../../services/api';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      skillSleep: {
        cardTitle: 'Skill Sleep',
        cardSubtitle: 'Validation-gated skill optimization runs',
        loadError: 'Failed to load Skill-Sleep runs',
        noRuns: 'No Skill-Sleep runs yet',
        noRunsHint: 'Run a round to propose and gate a skill improvement.',
        judgeDelta: 'Judge Δ',
        outcomeDelta: 'Outcome Δ',
        review: 'Review',
        adopted: 'Adopted',
        statusAccepted: 'Accepted',
        statusRejected: 'Rejected',
        statusAbstained: 'Abstained',
        statusFailed: 'Failed',
        statusNoCandidate: 'No candidate',
      },
    },
  },
});

function run(over: Record<string, unknown> = {}) {
  return {
    id: 1,
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
    candidate_body: 'body',
    current_body_hash: 'hash',
    reason: null,
    created_at: '2026-06-13 12:00:00',
    finished_at: '2026-06-13 12:05:00',
    adopted_at: null,
    outcome_before_score: 0.4,
    outcome_after_score: 0.6,
    outcome_delta: 0.2,
    outcome_question_count: 6,
    ...over,
  };
}

describe('SkillSleepCard', () => {
  let wrappers: Array<{ unmount: () => void }> = [];
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
  });

  function mountCard() {
    const w = mount(SkillSleepCard, {
      props: { projectId: 'proj-1' },
      global: { plugins: [i18n] },
    });
    wrappers.push(w);
    return w;
  }

  it('renders one row per run, scoped to the project', async () => {
    vi.mocked(skillSleepApi.listRuns).mockResolvedValue({ runs: [run(), run({ id: 2 })] } as never);
    const w = mountCard();
    await flushPromises();
    expect(skillSleepApi.listRuns).toHaveBeenCalledWith('proj-1');
    expect(w.findAll('[data-testid="skill-sleep-row"]')).toHaveLength(2);
    expect(w.find('.delta--up').exists()).toBe(true); // +0.3 judge delta
  });

  it('an accepted+un-adopted run shows Review and emits open-run on click', async () => {
    const r = run();
    vi.mocked(skillSleepApi.listRuns).mockResolvedValue({ runs: [r] } as never);
    const w = mountCard();
    await flushPromises();
    const btn = w.find('[data-testid="skill-sleep-review"]');
    expect(btn.exists()).toBe(true);
    await btn.trigger('click');
    expect(w.emitted('open-run')).toBeTruthy();
    expect((w.emitted('open-run')![0][0] as { id: number }).id).toBe(r.id);
  });

  it('an adopted run shows the Adopted badge and no Review', async () => {
    vi.mocked(skillSleepApi.listRuns).mockResolvedValue({
      runs: [run({ adopted_at: '2026-06-13 13:00:00' })],
    } as never);
    const w = mountCard();
    await flushPromises();
    expect(w.find('[data-testid="skill-sleep-review"]').exists()).toBe(false);
    expect(w.text()).toContain('Adopted');
  });

  it('a rejected run shows no Review affordance', async () => {
    vi.mocked(skillSleepApi.listRuns).mockResolvedValue({
      runs: [run({ status: 'rejected', delta: -0.1, adopted_at: null })],
    } as never);
    const w = mountCard();
    await flushPromises();
    expect(w.find('[data-testid="skill-sleep-review"]').exists()).toBe(false);
    expect(w.find('.delta--down').exists()).toBe(true);
  });

  it('empty list → EmptyState', async () => {
    vi.mocked(skillSleepApi.listRuns).mockResolvedValue({ runs: [] } as never);
    const w = mountCard();
    await flushPromises();
    expect(w.find('[data-testid="skill-sleep-empty"]').exists()).toBe(true);
  });

  it('api rejection → error branch', async () => {
    vi.mocked(skillSleepApi.listRuns).mockRejectedValue(new Error('boom'));
    const w = mountCard();
    await flushPromises();
    expect(w.find('.error-msg').exists()).toBe(true);
  });

  it('reload() re-fetches', async () => {
    vi.mocked(skillSleepApi.listRuns).mockResolvedValue({ runs: [] } as never);
    const w = mountCard();
    await flushPromises();
    expect(skillSleepApi.listRuns).toHaveBeenCalledTimes(1);
    await (w.vm as unknown as { reload: () => Promise<void> }).reload();
    await flushPromises();
    expect(skillSleepApi.listRuns).toHaveBeenCalledTimes(2);
  });
});
