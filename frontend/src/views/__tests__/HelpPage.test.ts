import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory, type Router } from 'vue-router';

vi.mock('../PluginSdkPage.vue', () => ({
  default: { name: 'SdkStub', template: '<div class="stub-sdk" />' },
}));
vi.mock('../GitHubActionsPage.vue', () => ({
  default: { name: 'GhaStub', template: '<div class="stub-gha" />' },
}));

import HelpPage from '../HelpPage.vue';

function makeRouter(initial = '/help'): Router {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/help', name: 'help', component: { template: '<div/>' } }],
  });
  router.push(initial);
  return router;
}

async function mountPage(initial = '/help') {
  const router = makeRouter(initial);
  await router.isReady();
  const wrapper = mount(HelpPage, { global: { plugins: [router] } });
  await flushPromises();
  return { wrapper, router };
}

describe('HelpPage', () => {
  it('renders two tabs and defaults to the Plugin SDK tab', async () => {
    const { wrapper } = await mountPage();
    expect(wrapper.findAll('[role="tab"]').length).toBe(2);
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Plugin SDK');
    expect(wrapper.find('.stub-sdk').exists()).toBe(true);
    expect(wrapper.find('#help-panel').exists()).toBe(true);
  });

  it('honors the initial ?tab= query (github-actions)', async () => {
    const { wrapper } = await mountPage('/help?tab=github-actions');
    expect(wrapper.find('.stub-gha').exists()).toBe(true);
    expect(wrapper.find('.stub-sdk').exists()).toBe(false);
  });
});
