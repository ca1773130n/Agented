import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { defineComponent, h } from 'vue';
import en from '../../locales/en.json';

const calls = vi.hoisted(() => ({
  list: vi.fn(),
}));

vi.mock('../../services/api', async (o) => ({
  ...(await o<Record<string, unknown>>()),
  projectApi: { list: calls.list },
}));

// Stub the heavy child so we only test the wrapper's picker/selection logic.
// Defined inside the factory to stay hoist-safe.
vi.mock('../ProjectResearchPage.vue', () => ({
  default: defineComponent({
    name: 'ProjectResearchPage',
    props: { projectId: { type: String, default: '' } },
    setup(props) {
      return () =>
        h('div', { class: 'project-research-stub', 'data-project-id': props.projectId });
    },
  }),
}));

// RouterLink stub so the empty-state link renders without a real router.
// Defined inside the factory to stay hoist-safe.
vi.mock('vue-router', async (o) => {
  const actual = await o<Record<string, unknown>>();
  return {
    ...actual,
    RouterLink: defineComponent({
      name: 'RouterLink',
      props: { to: { type: [String, Object], default: '' } },
      setup(_props, { slots }) {
        return () => h('a', { class: 'router-link-stub' }, slots.default?.());
      },
    }),
  };
});

import ResearchPage from '../ResearchPage.vue';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: { en: { surface: { research: en.surface.research } } } as never,
});

const mountPage = () =>
  mount(ResearchPage, {
    global: {
      plugins: [i18n],
    },
  });

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe('ResearchPage (top-level wrapper)', () => {
  it('defaults to projects[0] and passes it to ProjectResearchPage', async () => {
    calls.list.mockResolvedValue({ projects: [{ id: 'proj-a', name: 'A' }, { id: 'proj-b', name: 'B' }] });
    const w = mountPage();
    await flushPromises();
    expect(w.find('select').element.value).toBe('proj-a');
    const stub = w.find('.project-research-stub');
    expect(stub.exists()).toBe(true);
    expect(stub.attributes('data-project-id')).toBe('proj-a');
  });

  it('restores the last-used project from localStorage', async () => {
    localStorage.setItem('research:last-project', 'proj-b');
    calls.list.mockResolvedValue({ projects: [{ id: 'proj-a', name: 'A' }, { id: 'proj-b', name: 'B' }] });
    const w = mountPage();
    await flushPromises();
    expect(w.find('select').element.value).toBe('proj-b');
    expect(w.find('.project-research-stub').attributes('data-project-id')).toBe('proj-b');
  });

  it('falls back to projects[0] when the saved id no longer exists', async () => {
    localStorage.setItem('research:last-project', 'proj-gone');
    calls.list.mockResolvedValue({ projects: [{ id: 'proj-a', name: 'A' }] });
    const w = mountPage();
    await flushPromises();
    expect(w.find('select').element.value).toBe('proj-a');
  });

  it('renders the empty state (and NOT the child) when there are no projects', async () => {
    calls.list.mockResolvedValue({ projects: [] });
    const w = mountPage();
    await flushPromises();
    expect(w.find('.project-research-stub').exists()).toBe(false);
    expect(w.text()).toContain(en.surface.research.noProjects);
    expect(w.find('.research-empty-link').exists()).toBe(true);
  });

  it('remounts the child and persists the choice when the project is switched', async () => {
    calls.list.mockResolvedValue({ projects: [{ id: 'proj-a', name: 'A' }, { id: 'proj-b', name: 'B' }] });
    const w = mountPage();
    await flushPromises();
    await w.find('select').setValue('proj-b');
    await flushPromises();
    expect(w.find('.project-research-stub').attributes('data-project-id')).toBe('proj-b');
    expect(localStorage.getItem('research:last-project')).toBe('proj-b');
  });

  it('renders the localized picker label', async () => {
    calls.list.mockResolvedValue({ projects: [{ id: 'proj-a', name: 'A' }] });
    const w = mountPage();
    await flushPromises();
    expect(w.text()).toContain(en.surface.research.pickProject);
  });
});
