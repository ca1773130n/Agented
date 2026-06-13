/**
 * Tests for SkillSleepRoundControl:
 *   - body spreads only set optionals; measure always sent
 *   - in-flight disables Run; no skill → disabled
 *   - status-keyed result lines; emits completed except on error
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import SkillSleepRoundControl from '../SkillSleepRoundControl.vue';

vi.mock('../../../services/api', () => ({
  skillSleepApi: { runRound: vi.fn() },
  ApiError: class ApiError extends Error {},
}));

import { skillSleepApi } from '../../../services/api';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      skillSleep: {
        roundTitle: 'Optimize a skill',
        selectSkill: 'Select a skill…',
        optQuestions: 'Questions',
        optSeed: 'Seed',
        optEditBudget: 'Edit budget',
        optMeasure: 'Measure outcome',
        runRound: 'Run round',
        running: 'Running…',
        roundAccepted: 'Accepted ({delta})',
        roundNoCandidate: 'No change proposed',
        roundRejected: 'Rejected',
        roundAbstained: 'Abstained',
        roundFailed: 'Failed',
        roundError: 'Could not run round',
      },
    },
  },
});

const mockRun = skillSleepApi.runRound as ReturnType<typeof vi.fn>;

describe('SkillSleepRoundControl', () => {
  let wrappers: Array<{ unmount: () => void }> = [];
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
  });

  function mountControl() {
    const w = mount(SkillSleepRoundControl, {
      props: { projectId: 'proj-1', skills: [{ skill_name: 'deploy' }, { skill_name: 'review' }] },
      global: { plugins: [i18n] },
    });
    wrappers.push(w);
    return w;
  }

  it('disables Run until a skill is selected', async () => {
    const w = mountControl();
    const btn = () => w.find('[data-testid="ss-round-run"]').element as HTMLButtonElement;
    expect(btn().disabled).toBe(true);
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    expect(btn().disabled).toBe(false);
  });

  it('calls runRound for the selected skill, defaulting measure on and omitting unset optionals', async () => {
    // NOTE: the request-body spreading (only-set optionals, measure=false
    // serialised) is exhaustively unit-tested at the API layer in
    // services/api/__tests__/skill-sleep.test.ts. Here we verify the component
    // wiring: selected skill + the measure default reach runRound.
    mockRun.mockResolvedValue({ status: 'accepted', delta: 0.2 });
    const w = mountControl();
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    await w.find('[data-testid="ss-round-run"]').trigger('click');
    await flushPromises();
    const [projectId, skillName, body] = mockRun.mock.calls[0];
    expect(projectId).toBe('proj-1');
    expect(skillName).toBe('deploy');
    expect(body).toEqual({ measure: true });
    expect('n' in body).toBe(false);
    expect('edit_budget' in body).toBe(false);
  });

  it('renders an accepted result line and emits completed', async () => {
    mockRun.mockResolvedValue({ status: 'accepted', delta: 0.3 });
    const w = mountControl();
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    await w.find('[data-testid="ss-round-run"]').trigger('click');
    await flushPromises();
    expect(w.find('[data-testid="ss-round-result"]').text()).toContain('+30%');
    expect(w.emitted('completed')).toBeTruthy();
  });

  it('no_candidate still emits completed (a real, recorded outcome)', async () => {
    mockRun.mockResolvedValue({ status: 'no_candidate' });
    const w = mountControl();
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    await w.find('[data-testid="ss-round-run"]').trigger('click');
    await flushPromises();
    expect(w.find('[data-testid="ss-round-result"]').text()).toContain('No change proposed');
    expect(w.emitted('completed')).toBeTruthy();
  });

  it('an api error shows an error line and does NOT emit completed', async () => {
    mockRun.mockRejectedValue(new Error('boom'));
    const w = mountControl();
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    await w.find('[data-testid="ss-round-run"]').trigger('click');
    await flushPromises();
    expect(w.find('.ss-round__result--error').exists()).toBe(true);
    expect(w.emitted('completed')).toBeFalsy();
  });
});
