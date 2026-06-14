/**
 * Phase 20-04 (REQ-16) — GRD-route panel tests.
 *
 * Each panel mounts in happy-dom with no [Vue warn] and fires its expected
 * grdHarnessApi call. Collectively the seven panels exercise ALL 16 GRD routes
 * (asserted at the end). The HarnessPanelHost mounts over TabbedViewHost.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import type { Plugin } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createRouter, createMemoryHistory } from 'vue-router';
import enLocale from '../../../../locales/en.json';

const calls = vi.hoisted(() => ({
  getHealth: vi.fn().mockResolvedValue({ ok: true }),
  think: vi.fn().mockResolvedValue({ briefing: 'x' }),
  addDeadEnd: vi.fn().mockResolvedValue({}),
  promoteDeadEnds: vi.fn().mockResolvedValue({}),
  listDeadEnds: vi.fn().mockResolvedValue({ dead_ends: [] }),
  getGenome: vi.fn().mockResolvedValue({ g: 1 }),
  snapshotGenome: vi.fn().mockResolvedValue({}),
  listGenomeSnapshots: vi.fn().mockResolvedValue({ snapshots: [] }),
  latestGenomeSnapshot: vi.fn().mockResolvedValue({ g: 1 }),
  verifyMechanical: vi.fn().mockResolvedValue({ pass: true }),
  listPhaseReflections: vi.fn().mockResolvedValue({ reflections: [] }),
  verdictCounts: vi.fn().mockResolvedValue({ pass: 3 }),
  startEvolve: vi.fn().mockResolvedValue({ session_id: 's', evolve_run_id: 'e' }),
  listEvolveRuns: vi.fn().mockResolvedValue({ runs: [{ id: 'run-1', status: 'running' }] }),
  getEvolveRun: vi.fn().mockResolvedValue({ id: 'run-1', status: 'running' }),
  stopEvolveRun: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../../../services/api', async (orig) => {
  const actual = await orig<typeof import('../../../../services/api')>();
  return { ...actual, grdHarnessApi: calls };
});

import HealthPanel from '../panels/HealthPanel.vue';
import ThinkPanel from '../panels/ThinkPanel.vue';
import DeadEndsPanel from '../panels/DeadEndsPanel.vue';
import GenomePanel from '../panels/GenomePanel.vue';
import VerifyPanel from '../panels/VerifyPanel.vue';
import ReflectionsPanel from '../panels/ReflectionsPanel.vue';
import EvolvePanel from '../panels/EvolvePanel.vue';
import HarnessPanelHost from '../HarnessPanelHost.vue';

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: { surface: enLocale.surface } } as never,
  });
}
function makeRouter() {
  return createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] });
}
function opts(withRouter = false) {
  const plugins: Plugin[] = [makeI18n()];
  if (withRouter) plugins.push(makeRouter());
  return { global: { plugins, provide: { showToast: vi.fn() } } };
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

const P = { projectId: 'proj-1' };

describe('GRD-route panels', () => {
  it('HealthPanel calls getHealth', async () => {
    mount(HealthPanel, { props: P, ...opts() });
    await flushPromises();
    expect(calls.getHealth).toHaveBeenCalledWith('proj-1');
  });

  it('ThinkPanel calls think on run', async () => {
    const w = mount(ThinkPanel, { props: P, ...opts() });
    await w.find('.btn').trigger('click');
    await flushPromises();
    expect(calls.think).toHaveBeenCalledWith('proj-1');
  });

  it('DeadEndsPanel lists, adds, and promotes', async () => {
    const w = mount(DeadEndsPanel, { props: P, ...opts() });
    await flushPromises();
    expect(calls.listDeadEnds).toHaveBeenCalledWith('proj-1');
    const inputs = w.findAll('.form')[0].findAll('input');
    await inputs[0].setValue('approach-x');
    await inputs[1].setValue('reason-y');
    await w.findAll('.form')[0].find('.btn').trigger('click');
    await flushPromises();
    expect(calls.addDeadEnd).toHaveBeenCalled();
    const promoteInput = w.findAll('.form')[1].find('input');
    await promoteInput.setValue('05');
    await w.findAll('.form')[1].find('.btn').trigger('click');
    await flushPromises();
    expect(calls.promoteDeadEnds).toHaveBeenCalledWith('proj-1', '05');
  });

  it('GenomePanel loads genome/latest/snapshots and snapshots', async () => {
    const w = mount(GenomePanel, { props: P, ...opts() });
    await flushPromises();
    expect(calls.getGenome).toHaveBeenCalledWith('proj-1');
    expect(calls.latestGenomeSnapshot).toHaveBeenCalledWith('proj-1');
    expect(calls.listGenomeSnapshots).toHaveBeenCalledWith('proj-1');
    await w.find('.btn').trigger('click');
    await flushPromises();
    expect(calls.snapshotGenome).toHaveBeenCalledWith('proj-1');
  });

  it('VerifyPanel calls verifyMechanical with phase', async () => {
    const w = mount(VerifyPanel, { props: P, ...opts() });
    await w.find('input').setValue('07');
    await w.find('.btn').trigger('click');
    await flushPromises();
    expect(calls.verifyMechanical).toHaveBeenCalledWith('proj-1', '07');
  });

  it('ReflectionsPanel loads verdicts and reflections', async () => {
    const w = mount(ReflectionsPanel, { props: P, ...opts() });
    await flushPromises();
    expect(calls.verdictCounts).toHaveBeenCalledWith('proj-1');
    await w.find('input').setValue('03');
    await w.find('.btn').trigger('click');
    await flushPromises();
    expect(calls.listPhaseReflections).toHaveBeenCalledWith('proj-1', '03');
  });

  it('EvolvePanel lists, starts, opens, and stops runs', async () => {
    const w = mount(EvolvePanel, { props: P, ...opts() });
    await flushPromises();
    expect(calls.listEvolveRuns).toHaveBeenCalledWith('proj-1');
    await w.find('.rid').trigger('click');
    await flushPromises();
    expect(calls.getEvolveRun).toHaveBeenCalledWith('proj-1', 'run-1');
    const headBtns = w.findAll('.head-actions .btn');
    await headBtns[headBtns.length - 1].trigger('click');
    await flushPromises();
    expect(calls.startEvolve).toHaveBeenCalledWith('proj-1');
    await w.find('.row .btn').trigger('click');
    await flushPromises();
    expect(calls.stopEvolveRun).toHaveBeenCalledWith('proj-1', 'run-1');
  });

  it('HarnessPanelHost mounts over TabbedViewHost with 8 tabs', async () => {
    const w = mount(HarnessPanelHost, { props: P, ...opts(true) });
    await flushPromises();
    // 7 original panels + the new life-harness rounds panel.
    expect(w.findAll('[role="tab"]').length).toBe(8);
  });
});

describe('coverage: all 16 GRD routes exercised', () => {
  it('driving every panel calls all 16 Group-A GRD routes', async () => {
    const sixteen = [
      'getHealth', 'think', 'addDeadEnd', 'promoteDeadEnds', 'listDeadEnds',
      'getGenome', 'snapshotGenome', 'listGenomeSnapshots', 'latestGenomeSnapshot',
      'verifyMechanical', 'listPhaseReflections', 'verdictCounts',
      'startEvolve', 'listEvolveRuns', 'getEvolveRun', 'stopEvolveRun',
    ] as const;
    expect(sixteen.length).toBe(16);

    // Health
    mount(HealthPanel, { props: P, ...opts() });
    // Think
    const think = mount(ThinkPanel, { props: P, ...opts() });
    await think.find('.btn').trigger('click');
    // Dead-ends (list + add + promote)
    const de = mount(DeadEndsPanel, { props: P, ...opts() });
    await flushPromises();
    const dInputs = de.findAll('.form')[0].findAll('input');
    await dInputs[0].setValue('a');
    await dInputs[1].setValue('r');
    await de.findAll('.form')[0].find('.btn').trigger('click');
    await de.findAll('.form')[1].find('input').setValue('05');
    await de.findAll('.form')[1].find('.btn').trigger('click');
    // Genome (get/latest/list on mount + snapshot)
    const g = mount(GenomePanel, { props: P, ...opts() });
    await flushPromises();
    await g.find('.btn').trigger('click');
    // Verify
    const v = mount(VerifyPanel, { props: P, ...opts() });
    await v.find('input').setValue('07');
    await v.find('.btn').trigger('click');
    // Reflections (verdicts on mount + reflections)
    const rf = mount(ReflectionsPanel, { props: P, ...opts() });
    await rf.find('input').setValue('03');
    await rf.find('.btn').trigger('click');
    // Evolve (list on mount + open + start + stop)
    const ev = mount(EvolvePanel, { props: P, ...opts() });
    await flushPromises();
    await ev.find('.rid').trigger('click');
    const evBtns = ev.findAll('.head-actions .btn');
    await evBtns[evBtns.length - 1].trigger('click');
    await ev.find('.row .btn').trigger('click');
    await flushPromises();

    const uncovered = sixteen.filter((name) => calls[name].mock.calls.length === 0);
    expect(uncovered).toEqual([]);
  });
});
