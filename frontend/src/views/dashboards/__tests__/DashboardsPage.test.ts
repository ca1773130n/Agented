/**
 * PR-D — repurposed DashboardsPage renders the 4-tile lane index
 * + deep-link tiles, and tiles navigate to the matching lane route.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import { defineComponent, h } from 'vue';
import DashboardsPage from '../../DashboardsPage.vue';

vi.mock('../../../composables/useWebMcpTool', () => ({ useWebMcpTool: vi.fn() }));
vi.mock('../../../composables/useToast', () => ({ useToast: () => vi.fn() }));

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'dashboards', component: DashboardsPage },
      { path: '/dashboards/quality', name: 'dashboards-quality', component: defineComponent({ render: () => h('div', 'quality') }) },
      { path: '/dashboards/cost', name: 'dashboards-cost', component: defineComponent({ render: () => h('div', 'cost') }) },
      { path: '/dashboards/health', name: 'dashboards-health', component: defineComponent({ render: () => h('div', 'health') }) },
      { path: '/dashboards/activity', name: 'dashboards-activity', component: defineComponent({ render: () => h('div', 'activity') }) },
      { path: '/dashboards/products', name: 'products-summary', component: defineComponent({ render: () => h('div', 'products') }) },
      { path: '/dashboards/projects', name: 'projects-summary', component: defineComponent({ render: () => h('div', 'projects') }) },
      { path: '/dashboards/teams', name: 'teams-summary', component: defineComponent({ render: () => h('div', 'teams') }) },
      { path: '/dashboards/agents', name: 'agents-summary', component: defineComponent({ render: () => h('div', 'agents') }) },
    ],
  });
}

describe('PR-D DashboardsPage (4-tile lane index)', () => {
  let router: ReturnType<typeof buildRouter>;

  beforeEach(async () => {
    router = buildRouter();
    await router.push('/');
    await router.isReady();
  });

  it('renders exactly 4 lane tiles, one per lane', async () => {
    const w = mount(DashboardsPage, { global: { plugins: [router] } });
    const tiles = w.findAll('.lane-tile');
    expect(tiles.length).toBe(4);
    const names = tiles.map((t) => t.find('.lane-tile__name').text());
    expect(names).toEqual(['Quality', 'Cost', 'Health', 'Activity']);
  });

  it('renders the 3 deep-link tiles (Token Usage, Scheduling, Service Health)', () => {
    const w = mount(DashboardsPage, { global: { plugins: [router] } });
    const links = w.findAll('.deep-link');
    expect(links.length).toBe(3);
    const labels = links.map((l) => l.find('.deep-link__label').text());
    expect(labels).toEqual(['Token Usage', 'Scheduling', 'Service Health']);
  });

  it('clicking a lane tile navigates to that lane route', async () => {
    const push = vi.spyOn(router, 'push');
    const w = mount(DashboardsPage, { global: { plugins: [router] } });
    await w.find('[data-testid="lane-tile-dashboards-activity"]').trigger('click');
    expect(push).toHaveBeenCalledWith({ name: 'dashboards-activity' });
  });

  it('clicking the Scheduling deep-link routes to activity#scheduling', async () => {
    const push = vi.spyOn(router, 'push');
    const w = mount(DashboardsPage, { global: { plugins: [router] } });
    await w.find('[data-testid="deep-link-dashboards-activity#scheduling"]').trigger('click');
    expect(push).toHaveBeenCalledWith({ name: 'dashboards-activity', hash: '#scheduling' });
  });

  it('clicking the Service Health deep-link routes to health#service-health', async () => {
    const push = vi.spyOn(router, 'push');
    const w = mount(DashboardsPage, { global: { plugins: [router] } });
    await w.find('[data-testid="deep-link-dashboards-health#service-health"]').trigger('click');
    expect(push).toHaveBeenCalledWith({ name: 'dashboards-health', hash: '#service-health' });
  });

  it('renders 4 org-overview tiles (Products / Projects / Teams / Agents)', () => {
    const w = mount(DashboardsPage, { global: { plugins: [router] } });
    const tiles = w.findAll('.org-tile');
    expect(tiles.length).toBe(4);
    const labels = tiles.map((t) => t.find('.org-tile__label').text());
    expect(labels).toEqual(['Products', 'Projects', 'Teams', 'Agents']);
  });

  it('clicking an org tile navigates to that org-summary route', async () => {
    const push = vi.spyOn(router, 'push');
    const w = mount(DashboardsPage, { global: { plugins: [router] } });
    await w.find('[data-testid="org-tile-teams-summary"]').trigger('click');
    expect(push).toHaveBeenCalledWith({ name: 'teams-summary' });
  });
});
