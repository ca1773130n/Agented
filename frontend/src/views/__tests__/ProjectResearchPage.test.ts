/**
 * Phase 20-03 page test (REQ-15): ProjectResearchPage mounts in happy-dom with
 * no [Vue warn], composes the five research components over researchApi, and
 * wires QuestionIntake.submit -> useResearchSession.start.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import enLocale from '../../locales/en.json';

// ---------------------------------------------------------------------------
// Mocks — declared before the page import (vi.mock hoisting)
// ---------------------------------------------------------------------------
const mockGet = vi.fn();
const mockListThreads = vi.fn();
const mockGetThread = vi.fn();
const mockStart = vi.fn();

vi.mock('../../services/api', async () => {
  return {
    projectApi: { get: (...a: unknown[]) => mockGet(...a) },
    researchApi: {
      listThreads: (...a: unknown[]) => mockListThreads(...a),
      getThread: (...a: unknown[]) => mockGetThread(...a),
    },
  };
});

vi.mock('../../composables/useResearchSession', () => ({
  useResearchSession: () => ({
    sessionId: { value: null },
    threadId: { value: null },
    outputLines: { value: [] },
    status: { value: 'idle' },
    currentQuestion: { value: null },
    exitCode: { value: null },
    error: { value: null },
    start: (...a: unknown[]) => mockStart(...a),
    resume: vi.fn(),
    clearOutput: vi.fn(),
  }),
}));

vi.mock('../../composables/useToast', () => ({ useToast: () => vi.fn() }));

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-abc' } }),
}));

import ProjectResearchPage from '../ProjectResearchPage.vue';

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: { surface: enLocale.surface } } as never,
  });
}

// EntityLayout immediately renders its default slot; PlanningSessionPanel stubbed.
const stubs = {
  EntityLayout: {
    props: ['loadEntity'],
    async mounted() {
      await (this as unknown as { loadEntity: () => Promise<unknown> }).loadEntity();
    },
    template: '<div><slot /></div>',
  },
  PageHeader: { template: '<div><slot name="actions" /></div>' },
  PlanningSessionPanel: { template: '<div class="session-panel-stub" />' },
};

let warnSpy: ReturnType<typeof vi.spyOn>;

describe('ProjectResearchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockResolvedValue({ id: 'proj-abc', name: 'My Project' });
    mockListThreads.mockResolvedValue({
      threads: [
        { id: 'th-1', question: 'why blue?', status: 'running', iteration: 1, max_iterations: 5 },
      ],
    });
    mockGetThread.mockResolvedValue({
      id: 'th-1',
      thread: '# thread',
      hypotheses: '- rayleigh scattering',
      finding: '## Finding\n\nScattering.',
    });
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    // Exclude benign i18n "already been registered" warnings (fresh i18n per test).
    const vueWarns = warnSpy.mock.calls.filter(
      (c: unknown[]) =>
        String(c[0]).includes('[Vue warn]') && !String(c[0]).includes('already been registered'),
    );
    expect(vueWarns).toEqual([]);
    warnSpy.mockRestore();
  });

  it('mounts, loads threads, and renders the localized title + a thread row', async () => {
    const wrapper = mount(ProjectResearchPage, {
      props: { projectId: 'proj-abc' },
      global: { plugins: [makeI18n()], stubs },
    });
    await flushPromises();

    expect(mockListThreads).toHaveBeenCalledWith('proj-abc');
    expect(wrapper.text()).toContain('Research');
    expect(wrapper.text()).toContain('why blue?');
    // selected-thread bundle loaded
    expect(mockGetThread).toHaveBeenCalledWith('proj-abc', 'th-1');
    expect(wrapper.text()).toContain('rayleigh scattering');
    expect(wrapper.text()).toContain('Scattering');
  });

  it('starts a research run when QuestionIntake submits', async () => {
    const wrapper = mount(ProjectResearchPage, {
      props: { projectId: 'proj-abc' },
      global: { plugins: [makeI18n()], stubs },
    });
    await flushPromises();

    await wrapper.find('textarea').setValue('new question');
    await wrapper.find('form').trigger('submit');

    // QuestionIntake always forwards its steering mode; 'autopilot' is the default.
    expect(mockStart).toHaveBeenCalledWith('new question', { research_steering: 'autopilot' });
  });
});
