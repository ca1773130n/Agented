/**
 * Phase 20-03 component tests (REQ-15): the five research components mount in
 * happy-dom with no [Vue warn], render localized content, and emit correctly.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import enLocale from '../../../../locales/en.json';
import QuestionIntake from '../QuestionIntake.vue';
import ThreadList from '../ThreadList.vue';
import HypothesisLedger from '../HypothesisLedger.vue';
import ReportViewer from '../ReportViewer.vue';
import PortfolioRuns from '../PortfolioRuns.vue';
import type { ResearchThread } from '../../../../services/api/research';

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: { surface: enLocale.surface } } as never,
  });
}

const threads: ResearchThread[] = [
  { id: 'th-1', question: 'why is the sky blue?', status: 'running', iteration: 2, max_iterations: 5 },
  { id: 'th-2', question: 'what is dark matter?', status: 'complete', iteration: 5, max_iterations: 5 },
];

let warnSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
});
afterEach(() => {
  // Exclude benign "already been registered" warnings from re-creating a fresh
  // i18n instance per test (i18n-t/I18nT/etc.) — not a component-mount defect.
  const vueWarns = warnSpy.mock.calls.filter(
    (c: unknown[]) =>
      String(c[0]).includes('[Vue warn]') && !String(c[0]).includes('already been registered'),
  );
  expect(vueWarns).toEqual([]);
  warnSpy.mockRestore();
});

describe('QuestionIntake', () => {
  it('renders the prompt and emits submit with the trimmed question', async () => {
    const wrapper = mount(QuestionIntake, { global: { plugins: [makeI18n()] } });
    expect(wrapper.text()).toContain('Research question');
    await wrapper.find('textarea').setValue('  why is the sky blue?  ');
    await wrapper.find('form').trigger('submit');
    const emitted = wrapper.emitted('submit');
    expect(emitted).toBeTruthy();
    expect(emitted![0][0]).toBe('why is the sky blue?');
  });

  it('disables submit while a session is running', () => {
    const wrapper = mount(QuestionIntake, {
      props: { status: 'running' },
      global: { plugins: [makeI18n()] },
    });
    expect((wrapper.find('button[type="submit"]').element as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('ThreadList', () => {
  it('renders a row per thread with status + iteration and emits select', async () => {
    const wrapper = mount(ThreadList, {
      props: { threads, selectedId: 'th-1' },
      global: { plugins: [makeI18n()] },
    });
    expect(wrapper.text()).toContain('why is the sky blue?');
    expect(wrapper.text()).toContain('2 / 5');
    expect(wrapper.text()).toContain('Running');
    await wrapper.findAll('.tl-row')[1].trigger('click');
    expect(wrapper.emitted('select')![0][0]).toBe('th-2');
  });

  it('shows the empty state when there are no threads', () => {
    const wrapper = mount(ThreadList, {
      props: { threads: [] },
      global: { plugins: [makeI18n()] },
    });
    expect(wrapper.text()).toContain('No research threads yet.');
  });
});

describe('HypothesisLedger', () => {
  it('renders markdown ledger content', () => {
    const wrapper = mount(HypothesisLedger, {
      props: { hypotheses: '# H1\n\n- rayleigh scattering' },
      global: { plugins: [makeI18n()] },
    });
    expect(wrapper.find('.hl-body').html()).toContain('rayleigh scattering');
  });

  it('shows the empty state when no hypotheses', () => {
    const wrapper = mount(HypothesisLedger, {
      props: { hypotheses: null },
      global: { plugins: [makeI18n()] },
    });
    expect(wrapper.text()).toContain('No hypotheses recorded yet.');
  });
});

describe('ReportViewer', () => {
  it('renders FINDING markdown via the green renderer', () => {
    const wrapper = mount(ReportViewer, {
      props: { finding: '## Finding\n\nThe sky scatters blue light.' },
      global: { plugins: [makeI18n()] },
    });
    expect(wrapper.find('.rv-body').html()).toContain('scatters blue light');
  });

  it('shows the empty state when no finding', () => {
    const wrapper = mount(ReportViewer, {
      props: { finding: '' },
      global: { plugins: [makeI18n()] },
    });
    expect(wrapper.text()).toContain('No report available yet.');
  });
});

describe('PortfolioRuns', () => {
  it('aggregates thread counts', () => {
    const wrapper = mount(PortfolioRuns, {
      props: { threads },
      global: { plugins: [makeI18n()] },
    });
    const text = wrapper.text();
    expect(text).toContain('Portfolio');
    // 2 total, 1 running, 1 completed, 7 iterations
    expect(text).toContain('2');
    expect(text).toContain('7');
  });
});
