/**
 * Phase 20-04 (REQ-16) — autonomy / rounds / shared-forge component tests.
 *
 * Asserts: AutonomyEditor PUTs the edited policy; RoundDetail does NOT call
 * revertRound until the confirmation step is taken, then DOES (the destructive
 * revert confirm-guard); SharedForgeBrowser adopt calls adoptShared with the
 * binding id. All mount in happy-dom with no [Vue warn].
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import enLocale from '../../../../locales/en.json';

vi.mock('../../../../services/api', async (orig) => {
  const actual = await orig<typeof import('../../../../services/api')>();
  return {
    ...actual,
    grdHarnessApi: {
      getAutonomy: vi.fn().mockResolvedValue({
        project_id: 'proj-1',
        policy: { auto_plan: false, auto_execute: false, auto_verify: false, max_rounds: 2 },
        configured: true,
      }),
      setAutonomy: vi.fn().mockResolvedValue({ project_id: 'proj-1', policy: {} }),
      listProjectRounds: vi
        .fn()
        .mockResolvedValue({ project_id: 'proj-1', rounds: [{ round_id: 'r-1', status: 'applied' }] }),
      listAllRounds: vi.fn().mockResolvedValue({ rounds: [] }),
      getRoundDetail: vi.fn().mockResolvedValue({ round_id: 'r-1', status: 'applied' }),
      getRoundImpact: vi.fn().mockResolvedValue({ window: 20 }),
      approveRound: vi.fn().mockResolvedValue({}),
      abortRound: vi.fn().mockResolvedValue({}),
      revertRound: vi.fn().mockResolvedValue({ round_id: 'r-1' }),
      listSharedForge: vi.fn().mockResolvedValue({ shared: [{ id: 7 }] }),
      adoptShared: vi.fn().mockResolvedValue({ project_id: 'proj-1' }),
    },
  };
});

import { grdHarnessApi } from '../../../../services/api';
import AutonomyEditor from '../AutonomyEditor.vue';
import RoundList from '../RoundList.vue';
import RoundDetail from '../RoundDetail.vue';
import SharedForgeBrowser from '../SharedForgeBrowser.vue';

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: { surface: enLocale.surface } } as never,
  });
}

function mountOpts() {
  return {
    global: {
      plugins: [makeI18n()],
      provide: { showToast: vi.fn() },
    },
  };
}

let warnSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.clearAllMocks();
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
});
afterEach(() => {
  const vueWarns = warnSpy.mock.calls.filter(
    (c: unknown[]) =>
      String(c[0]).includes('[Vue warn]') && !String(c[0]).includes('already been registered'),
  );
  expect(vueWarns).toEqual([]);
  warnSpy.mockRestore();
});

describe('AutonomyEditor', () => {
  it('reads the policy and PUTs the edited policy on save', async () => {
    const wrapper = mount(AutonomyEditor, { props: { projectId: 'proj-1' }, ...mountOpts() });
    await flushPromises();
    expect(grdHarnessApi.getAutonomy).toHaveBeenCalledWith('proj-1');

    // Toggle auto_plan on, then save.
    await wrapper.findAll('.toggle')[0].trigger('click');
    await wrapper.find('.btn-primary').trigger('click');
    await flushPromises();

    expect(grdHarnessApi.setAutonomy).toHaveBeenCalledTimes(1);
    const [pid, policy] = (grdHarnessApi.setAutonomy as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(pid).toBe('proj-1');
    expect(policy.auto_plan).toBe(true);
    expect(policy.max_rounds).toBe(2);
  });
});

describe('RoundList', () => {
  it('lists project rounds and emits select', async () => {
    const wrapper = mount(RoundList, { props: { projectId: 'proj-1' }, ...mountOpts() });
    await flushPromises();
    expect(grdHarnessApi.listProjectRounds).toHaveBeenCalledWith('proj-1');
    await wrapper.find('.row').trigger('click');
    expect(wrapper.emitted('select')?.[0]).toEqual(['r-1']);
  });
});

describe('RoundDetail revert confirm-guard', () => {
  it('does NOT call revertRound until confirmation, then DOES', async () => {
    const wrapper = mount(RoundDetail, { props: { roundId: 'r-1' }, ...mountOpts() });
    await flushPromises();
    expect(grdHarnessApi.getRoundDetail).toHaveBeenCalledWith('r-1');

    // Click "Revert" — must NOT hit the API (guard step 1).
    await wrapper.find('.btn-danger').trigger('click');
    await flushPromises();
    expect(grdHarnessApi.revertRound).not.toHaveBeenCalled();

    // Confirmation UI is now shown.
    expect(wrapper.find('.revert-confirm').exists()).toBe(true);

    // Explicit confirm — NOW it hits the API (guard step 2).
    const dangerButtons = wrapper.findAll('.revert-confirm .btn-danger');
    await dangerButtons[dangerButtons.length - 1].trigger('click');
    await flushPromises();
    expect(grdHarnessApi.revertRound).toHaveBeenCalledWith('r-1');
  });
});

describe('SharedForgeBrowser', () => {
  it('adopts a binding by id', async () => {
    const wrapper = mount(SharedForgeBrowser, { props: { projectId: 'proj-1' }, ...mountOpts() });
    await flushPromises();
    expect(grdHarnessApi.listSharedForge).toHaveBeenCalled();
    await wrapper.find('.row .btn').trigger('click');
    await flushPromises();
    expect(grdHarnessApi.adoptShared).toHaveBeenCalledWith('proj-1', 7);
  });
});
