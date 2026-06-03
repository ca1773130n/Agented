import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory, type Router } from 'vue-router';

// Mock the five tab views so mounting doesn't pull in the real (API-calling)
// views — each becomes a trivial marker component.
vi.mock('../ConditionalTriggerRulesPage.vue', () => ({
  default: { name: 'CondStub', template: '<div class="stub-conditions" />' },
}));
vi.mock('../NLTriggerRuleEditor.vue', () => ({
  default: { name: 'NlStub', template: '<div class="stub-nl" />' },
}));
vi.mock('../VisualCronWizard.vue', () => ({
  default: { name: 'CronStub', template: '<div class="stub-schedule" />' },
}));
vi.mock('../WebhookPayloadTransformerPage.vue', () => ({
  default: { name: 'PayloadStub', template: '<div class="stub-payload" />' },
}));
vi.mock('../BotDryRun.vue', () => ({
  default: { name: 'DryRunStub', template: '<div class="stub-dryrun" />' },
}));

import TriggerToolsPage from '../TriggerToolsPage.vue';

function makeRouter(initial = '/trigger-tools'): Router {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/trigger-tools', name: 'trigger-tools', component: { template: '<div/>' } }],
  });
  router.push(initial);
  return router;
}

async function mountPage(initial = '/trigger-tools') {
  const router = makeRouter(initial);
  await router.isReady();
  const wrapper = mount(TriggerToolsPage, { global: { plugins: [router] } });
  await flushPromises();
  return { wrapper, router };
}

describe('TriggerToolsPage', () => {
  it('renders five tabs with the existing localized labels', async () => {
    const { wrapper } = await mountPage();
    const tabs = wrapper.findAll('[role="tab"]');
    expect(tabs.length).toBe(5);
    const labels = tabs.map((t) => t.text());
    expect(labels).toContain('Trigger Conditions');
    expect(labels).toContain('NL Rule Editor');
    expect(labels).toContain('Payload Transformer');
    expect(labels).toContain('Bot Dry-Run');
    // ids use the trigger-tools prefix (distinct from the integrations host).
    expect(wrapper.find('#trigger-tools-tab-conditions').exists()).toBe(true);
    expect(wrapper.find('#trigger-tools-panel').exists()).toBe(true);
  });

  it('defaults to the conditions tab and mounts only that view', async () => {
    const { wrapper } = await mountPage();
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Trigger Conditions');
    expect(wrapper.find('.stub-conditions').exists()).toBe(true);
    expect(wrapper.find('.stub-dryrun').exists()).toBe(false);
  });

  it('honors the initial ?tab= query (dry-run)', async () => {
    const { wrapper } = await mountPage('/trigger-tools?tab=dry-run');
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toBe('Bot Dry-Run');
    expect(wrapper.find('.stub-dryrun').exists()).toBe(true);
  });

  it('preserves other query params when switching tabs (e.g. trigger_id)', async () => {
    const { wrapper, router } = await mountPage('/trigger-tools?trigger_id=trig-abc');
    const payloadTab = wrapper.findAll('[role="tab"]').find((t) => t.text() === 'Payload Transformer');
    await payloadTab!.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.query.tab).toBe('payload');
    expect(router.currentRoute.value.query.trigger_id).toBe('trig-abc');
  });
});
