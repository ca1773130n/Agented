/**
 * Tests for SkillSleepRoundControl:
 *   - body spreads only set optionals; measure always sent
 *   - in-flight disables Run; no skill → disabled
 *   - a round runs in the BACKGROUND: runRound returns a job_id, the component
 *     polls roundStatus for the verdict, stays "running" meanwhile, and stops
 *     polling on unmount (so the operator can leave the page).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import SkillSleepRoundControl from '../SkillSleepRoundControl.vue';

vi.mock('../../../services/api', () => ({
  skillSleepApi: { runRound: vi.fn(), roundStatus: vi.fn() },
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
const mockStatus = skillSleepApi.roundStatus as ReturnType<typeof vi.fn>;

describe('SkillSleepRoundControl', () => {
  let wrappers: Array<{ unmount: () => void }> = [];
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    // Default: the round finishes accepted on the first poll.
    mockRun.mockResolvedValue({ job_id: 'job-1' });
    mockStatus.mockResolvedValue({ status: 'done', verdict: { status: 'accepted', delta: 0.3 } });
  });
  afterEach(() => {
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
    vi.useRealTimers();
  });

  function mountControl() {
    const w = mount(SkillSleepRoundControl, {
      props: { projectId: 'proj-1', skills: [{ skill_name: 'deploy' }, { skill_name: 'review' }] },
      global: { plugins: [i18n] },
    });
    wrappers.push(w);
    return w;
  }

  // Kick a round and advance through one poll tick.
  async function runAndPoll(w: ReturnType<typeof mountControl>) {
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    await w.find('[data-testid="ss-round-run"]').trigger('click');
    await flushPromises(); // runRound resolves → schedules the poll
    await vi.advanceTimersByTimeAsync(3000); // fire the poll → roundStatus
    await flushPromises();
  }

  it('disables Run until a skill is selected', async () => {
    const w = mountControl();
    const btn = () => w.find('[data-testid="ss-round-run"]').element as HTMLButtonElement;
    expect(btn().disabled).toBe(true);
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    expect(btn().disabled).toBe(false);
  });

  it('calls runRound for the selected skill, defaulting measure on and omitting unset optionals', async () => {
    const w = mountControl();
    await runAndPoll(w);
    const [projectId, skillName, body] = mockRun.mock.calls[0];
    expect(projectId).toBe('proj-1');
    expect(skillName).toBe('deploy');
    expect(body).toEqual({ measure: true });
    expect('n' in body).toBe(false);
    expect('edit_budget' in body).toBe(false);
  });

  it('stays "running" while polling, then renders the verdict and emits completed', async () => {
    // First poll still running, second poll done — proves it does not block.
    mockStatus
      .mockResolvedValueOnce({ status: 'running' })
      .mockResolvedValueOnce({ status: 'done', verdict: { status: 'accepted', delta: 0.3 } });
    const w = mountControl();
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    await w.find('[data-testid="ss-round-run"]').trigger('click');
    await flushPromises();
    const btn = w.find('[data-testid="ss-round-run"]').element as HTMLButtonElement;
    expect(btn.textContent).toContain('Running…');
    expect(btn.disabled).toBe(true);

    await vi.advanceTimersByTimeAsync(3000); // poll 1 → running
    await flushPromises();
    expect(w.find('[data-testid="ss-round-result"]').exists()).toBe(false);

    await vi.advanceTimersByTimeAsync(3000); // poll 2 → done
    await flushPromises();
    expect(w.find('[data-testid="ss-round-result"]').text()).toContain('+30%');
    expect(w.emitted('completed')).toBeTruthy();
  });

  it('surfaces a background-round error without emitting completed', async () => {
    mockStatus.mockResolvedValue({ status: 'error', error: 'reflect blew up' });
    const w = mountControl();
    await runAndPoll(w);
    expect(w.find('.ss-round__result--error').text()).toContain('reflect blew up');
    expect(w.emitted('completed')).toBeFalsy();
  });

  it('a failed trigger shows an error line and does NOT emit completed', async () => {
    mockRun.mockRejectedValue(new Error('boom'));
    const w = mountControl();
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    await w.find('[data-testid="ss-round-run"]').trigger('click');
    await flushPromises();
    expect(w.find('.ss-round__result--error').exists()).toBe(true);
    expect(w.emitted('completed')).toBeFalsy();
  });

  it('stops polling on unmount (operator can leave the page)', async () => {
    mockStatus.mockResolvedValue({ status: 'running' });
    const w = mountControl();
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    await w.find('[data-testid="ss-round-run"]').trigger('click');
    await flushPromises();
    await vi.advanceTimersByTimeAsync(3000);
    await flushPromises();
    const callsBefore = mockStatus.mock.calls.length;
    w.unmount();
    wrappers = wrappers.filter((x) => x !== w);
    await vi.advanceTimersByTimeAsync(9000);
    await flushPromises();
    expect(mockStatus.mock.calls.length).toBe(callsBefore); // no further polls
  });

  it('does NOT reschedule when unmounted while a poll request is in flight', async () => {
    // Regression (codex Medium): the timer clears itself before awaiting, so
    // onBeforeUnmount has nothing to cancel — the `stopped` guard must prevent
    // the resolved request from scheduling another poll after unmount.
    let resolveStatus!: (v: { status: string }) => void;
    mockStatus.mockReturnValueOnce(
      new Promise((res) => {
        resolveStatus = res;
      }),
    );
    const w = mountControl();
    await w.find('[data-testid="ss-round-skill"]').setValue('deploy');
    await w.find('[data-testid="ss-round-run"]').trigger('click');
    await flushPromises();
    await vi.advanceTimersByTimeAsync(3000); // poll fires → roundStatus in flight (pending)
    await flushPromises();

    w.unmount(); // unmount WHILE the request is pending
    wrappers = wrappers.filter((x) => x !== w);
    resolveStatus({ status: 'running' }); // would normally schedule another poll
    await flushPromises();
    const callsAfter = mockStatus.mock.calls.length;

    await vi.advanceTimersByTimeAsync(9000);
    await flushPromises();
    expect(mockStatus.mock.calls.length).toBe(callsAfter); // no reschedule after unmount
  });
});
