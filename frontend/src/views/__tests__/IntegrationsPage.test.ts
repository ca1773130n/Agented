import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory, type Router } from 'vue-router';

// Mock the three tab views so mounting IntegrationsPage doesn't pull in the
// real (heavy, API-calling) views. Each becomes a trivial marker component.
vi.mock('../TeamsNotificationChannelsPage.vue', () => ({
  default: { name: 'ChannelsStub', template: '<div class="stub-channels" />' },
}));
vi.mock('../SlackNotificationsPage.vue', () => ({
  default: { name: 'SlackStub', template: '<div class="stub-slack" />' },
}));
vi.mock('../IntegrationTicketing.vue', () => ({
  default: { name: 'TicketingStub', template: '<div class="stub-ticketing" />' },
}));

import IntegrationsPage from '../IntegrationsPage.vue';

function makeRouter(initial = '/integrations'): Router {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/integrations', name: 'integrations', component: { template: '<div/>' } }],
  });
  router.push(initial);
  return router;
}

async function mountPage(initial = '/integrations') {
  const router = makeRouter(initial);
  await router.isReady();
  const wrapper = mount(IntegrationsPage, { global: { plugins: [router] } });
  await flushPromises(); // resolve the async tab component
  return { wrapper, router };
}

describe('IntegrationsPage', () => {
  it('renders three tabs with the existing localized labels', async () => {
    const { wrapper } = await mountPage();
    const tabs = wrapper.findAll('[role="tab"]');
    expect(tabs.length).toBe(3);
    const labels = tabs.map((t) => t.text());
    expect(labels).toEqual(['Notification Channels', 'Slack Notifications', 'Jira / Linear']);
  });

  it('defaults to the channels tab and mounts only the channels view', async () => {
    const { wrapper } = await mountPage();
    const active = wrapper.find('[role="tab"][aria-selected="true"]');
    expect(active.text()).toBe('Notification Channels');
    expect(wrapper.find('.stub-channels').exists()).toBe(true);
    expect(wrapper.find('.stub-slack').exists()).toBe(false);
    expect(wrapper.find('.stub-ticketing').exists()).toBe(false);
  });

  it('honors the initial ?tab= query (slack)', async () => {
    const { wrapper } = await mountPage('/integrations?tab=slack');
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Slack Notifications');
    expect(wrapper.find('.stub-slack').exists()).toBe(true);
    expect(wrapper.find('.stub-channels').exists()).toBe(false);
  });

  it('falls back to the channels tab for an unknown ?tab= value', async () => {
    const { wrapper } = await mountPage('/integrations?tab=bogus');
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Notification Channels');
  });

  it('switches tab and reflects it in the URL query on click', async () => {
    const { wrapper, router } = await mountPage();
    const ticketingTab = wrapper.findAll('[role="tab"]').find((t) => t.text() === 'Jira / Linear');
    expect(ticketingTab).toBeTruthy();
    await ticketingTab!.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.query.tab).toBe('ticketing');
    expect(wrapper.find('.stub-ticketing').exists()).toBe(true);
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Jira / Linear');
  });
});
