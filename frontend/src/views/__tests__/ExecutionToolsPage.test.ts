import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory, type Router } from 'vue-router';

vi.mock('../ExecutionSearchPage.vue', () => ({
  default: { name: 'SearchStub', template: '<div class="stub-search" />' },
}));
vi.mock('../ExecutionTaggingPage.vue', () => ({
  default: { name: 'TaggingStub', template: '<div class="stub-tagging" />' },
}));
vi.mock('../ExecutionReplayDiff.vue', () => ({
  default: { name: 'ReplayStub', template: '<div class="stub-replay" />' },
}));
vi.mock('../ExecutionAnnotation.vue', () => ({
  default: { name: 'AnnStub', template: '<div class="stub-annotations" />' },
}));

import ExecutionToolsPage from '../ExecutionToolsPage.vue';

function makeRouter(initial = '/execution-tools'): Router {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/execution-tools', name: 'execution-tools', component: { template: '<div/>' } }],
  });
  router.push(initial);
  return router;
}

async function mountPage(initial = '/execution-tools') {
  const router = makeRouter(initial);
  await router.isReady();
  const wrapper = mount(ExecutionToolsPage, { global: { plugins: [router] } });
  await flushPromises();
  return { wrapper, router };
}

describe('ExecutionToolsPage', () => {
  it('renders four tabs and defaults to search', async () => {
    const { wrapper } = await mountPage();
    const tabs = wrapper.findAll('[role="tab"]');
    expect(tabs.length).toBe(4);
    expect(tabs.map((t) => t.text())).toContain('Execution Search');
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Execution Search');
    expect(wrapper.find('.stub-search').exists()).toBe(true);
    // ids use the execution-tools prefix (distinct from other hosts).
    expect(wrapper.find('#execution-tools-panel').exists()).toBe(true);
    expect(wrapper.find('#execution-tools-tab-search').exists()).toBe(true);
  });

  it('honors the initial ?tab= query (annotations)', async () => {
    const { wrapper } = await mountPage('/execution-tools?tab=annotations');
    expect(wrapper.find('.stub-annotations').exists()).toBe(true);
    expect(wrapper.find('.stub-search').exists()).toBe(false);
  });

  it('switches to the replay tab on click and reflects it in the URL', async () => {
    const { wrapper, router } = await mountPage();
    await wrapper.find('#execution-tools-tab-replay').trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.query.tab).toBe('replay');
    expect(wrapper.find('.stub-replay').exists()).toBe(true);
  });
});
