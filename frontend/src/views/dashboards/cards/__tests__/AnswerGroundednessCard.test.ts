/**
 * TDD tests for AnswerGroundednessCard:
 *   - renders delta stats from mocked api
 *   - shows project name
 *   - shows empty state when no runs
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import AnswerGroundednessCard from '../AnswerGroundednessCard.vue';

vi.mock('../../../../services/api', () => ({
  answerEvalApi: { listRuns: vi.fn() },
}));

import { answerEvalApi } from '../../../../services/api';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      answerEval: {
        cardTitle: 'Answer Groundedness',
        cardSubtitle: 'Pipeline vs baseline — latest eval run',
        groundedness: 'Groundedness',
        sufficiency: 'Sufficiency',
        quality: 'Quality',
        noRuns: 'No eval runs yet',
        noRunsHint: 'Run an eval to see quality metrics',
        projectLabel: 'Project',
        loadError: 'Failed to load',
        statusRunning: 'Running',
        statusComplete: 'Complete',
        statusFailed: 'Failed',
      },
    },
  },
});

const COMPLETE_RUN = {
  id: 1,
  project_id: 'proj-abc',
  project_name: 'My Project',
  question_count: 8,
  judge_backend: 'claude',
  baseline_groundedness: 0.6,
  baseline_sufficiency: 0.55,
  baseline_quality: 0.5,
  pipeline_groundedness: 0.8,
  pipeline_sufficiency: 0.75,
  pipeline_quality: 0.7,
  delta_groundedness: 0.2,
  delta_sufficiency: 0.2,
  delta_quality: 0.2,
  status: 'complete' as const,
  created_at: '2026-06-10T00:00:00',
  finished_at: '2026-06-10T00:05:00',
};

describe('AnswerGroundednessCard', () => {
  let wrappers: Array<{ unmount: () => void }> = [];

  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
  });

  function mountCard() {
    const wrapper = mount(AnswerGroundednessCard, {
      global: { plugins: [i18n] },
    });
    wrappers.push(wrapper);
    return wrapper;
  }

  it('renders delta stats for the latest finished run', async () => {
    vi.mocked(answerEvalApi.listRuns).mockResolvedValue({ runs: [COMPLETE_RUN] } as never);

    const wrapper = mountCard();
    await flushPromises();

    expect(answerEvalApi.listRuns).toHaveBeenCalledWith(undefined);

    const text = wrapper.text();
    // Project name
    expect(text).toContain('My Project');
    // Delta values rendered (as percentages or decimals)
    expect(text).toMatch(/0\.20|20%|\+0\.20|\+20/);
  });

  it('shows empty state when no runs exist', async () => {
    vi.mocked(answerEvalApi.listRuns).mockResolvedValue({ runs: [] } as never);

    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.find('[data-testid="answer-eval-empty"]').exists()).toBe(true);
  });

  it('shows empty state when all runs are non-complete', async () => {
    vi.mocked(answerEvalApi.listRuns).mockResolvedValue({
      runs: [{ ...COMPLETE_RUN, status: 'running' }],
    } as never);

    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.find('[data-testid="answer-eval-empty"]').exists()).toBe(true);
  });

  it('up-arrow styling on positive delta', async () => {
    vi.mocked(answerEvalApi.listRuns).mockResolvedValue({ runs: [COMPLETE_RUN] } as never);

    const wrapper = mountCard();
    await flushPromises();

    // At least one positive delta chip present
    expect(wrapper.find('.delta--up').exists()).toBe(true);
  });

  it('down-arrow styling on negative delta', async () => {
    const negativeRun = {
      ...COMPLETE_RUN,
      delta_groundedness: -0.1,
      delta_sufficiency: -0.05,
      delta_quality: -0.08,
    };
    vi.mocked(answerEvalApi.listRuns).mockResolvedValue({ runs: [negativeRun] } as never);

    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.find('.delta--down').exists()).toBe(true);
  });

  it('emits loaded event after data fetch', async () => {
    vi.mocked(answerEvalApi.listRuns).mockResolvedValue({ runs: [COMPLETE_RUN] } as never);

    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.emitted('loaded')).toBeTruthy();
    expect(wrapper.emitted('loaded')![0]).toEqual(['answer-groundedness']);
  });
});
