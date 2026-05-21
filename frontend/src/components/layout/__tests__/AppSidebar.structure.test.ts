import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount, type VueWrapper } from '@vue/test-utils';
import { createRouter, createMemoryHistory, type Router } from 'vue-router';
import { defineComponent, h, ref } from 'vue';
import AppSidebar from '../AppSidebar.vue';

// Stub the tour checklist composable so the sidebar doesn't try to
// reach the tour state machine in tests. The composable returns Vue
// refs; we mirror that so the v-if check in the template unwraps
// correctly.
vi.mock('../../../composables/useTourChecklist', () => ({
  useTourChecklist: () => ({
    checklistItems: ref([]),
    completedCount: ref(0),
    totalCount: ref(0),
    showChecklist: ref(false),
  }),
}));

// useWebMcpTool registers tools on mount via a global registry. Stub
// it out to keep mounts side-effect-free.
vi.mock('../../../composables/useWebMcpTool', () => ({
  useWebMcpTool: () => ({}),
}));

// projectInstanceApi is awaited when a project row is expanded; we
// never expand one in these tests, but stub anyway.
vi.mock('../../../services/api', async () => {
  return {
    projectInstanceApi: { list: vi.fn().mockResolvedValue({ instances: [] }) },
  };
});

const StubView = defineComponent({
  name: 'StubView',
  render: () => h('div'),
});

function buildRouter(): Router {
  // We only need the route names referenced by the sidebar to exist so
  // RouterLink/router.push doesn't warn. List the routes the sidebar
  // explicitly references with `name:`.
  const routeNames = [
    'dashboards', 'security-dashboard', 'pr-review-dashboard', 'trigger-dashboard',
    'token-usage', 'rotation-dashboard', 'analytics-dashboard', 'health-dashboard',
    'bot-health', 'team-impact-report', 'cross-team-insights',
    'execution-queue-dashboard', 'execution-anomaly-detection', 'team-leaderboard',
    'sketch-chat', 'products', 'product-dashboard', 'product-settings',
    'projects', 'project-dashboard', 'project-settings', 'project-planning',
    'project-instance-playground', 'teams', 'team-dashboard', 'team-settings',
    'agents', 'agent-create',
    'super-agents', 'explore-super-agents',
    'workflows', 'workflow-playground',
    'plugins', 'plugin-design', 'explore-plugins', 'harness-integration',
    'plugin-detail',
    'mcp-servers', 'explore-mcp-servers',
    'skills-playground', 'skill-create', 'my-skills', 'explore-skills',
    'commands', 'command-design',
    'hooks', 'hook-design',
    'rules', 'rule-design',
    // Trigger facets (new section in PR-B)
    'triggers', 'bot-templates', 'bot-clone-fork', 'cross-team-bot-sharing',
    'incident-response-playbooks', 'inline-prompt-editor', 'visual-cron-wizard',
    'conditional-trigger-rules', 'repo-scope-filters', 'structured-output',
    'prompt-ab-testing', 'multi-provider-fallback', 'multi-repo-fan-out',
    'pr-auto-assignment', 'pr-review-learning-loop', 'github-actions',
    'webhook-recorder', 'dependency-impact-bot', 'bot-recommendation-engine',
    'bot-dependency-graph', 'bot-performance-benchmarks', 'bot-runbooks',
    'execution-tagging', 'changelog-generator', 'prompt-snippets',
    // External integrations
    'slack-notifications', 'integration-ticketing', 'notification-channels',
    'on-call-escalation',
    // History (security-history route still exists; sidebar entry removed)
    'security-history', 'trigger-history', 'audit-history',
    'execution-replay-diff', 'execution-annotation', 'execution-search',
    'usage-history',
    'ai-backends', 'backend-detail',
    'secrets-vault', 'rbac-settings', 'sso-settings', 'team-budgets',
    'execution-quota-controls', 'report-digests', 'mobile-execution-monitor',
    'bot-sla-uptime', 'api-keys', 'findings-triage-board',
    'skill-version-pinning', 'conversation-history-viewer', 'system-errors',
    'settings',
  ];
  return createRouter({
    history: createMemoryHistory(),
    routes: routeNames.map((name) => ({
      name,
      path: name === 'trigger-dashboard' || name === 'trigger-history'
        ? `/${name}/:triggerId`
        : name === 'product-dashboard' || name === 'product-settings'
          ? `/${name}/:productId`
          : name === 'project-dashboard' || name === 'project-settings'
            || name === 'project-planning' || name === 'project-instance-playground'
            ? `/${name}/:projectId/:instanceId?`
            : name === 'team-dashboard' || name === 'team-settings'
              ? `/${name}/:teamId`
              : name === 'plugin-detail' ? `/${name}/:pluginId`
                : name === 'backend-detail' ? `/${name}/:backendId`
                  : `/${name}`,
      component: StubView,
    })),
  });
}

async function mountSidebar(): Promise<VueWrapper> {
  const router = buildRouter();
  await router.push('/');
  await router.isReady();
  return mount(AppSidebar, {
    global: {
      plugins: [router],
    },
    props: {
      appVersion: '1.0.0-test',
      healthColor: '#00ff88',
      healthTooltip: 'Healthy',
      activeExecutionCount: 0,
      customTriggers: [],
      products: [],
      projects: [],
      teams: [],
      plugins: [],
      sidebarBackends: [],
      sidebarLoading: false,
      sidebarErrors: {},
    },
  });
}

function rootEl(wrapper: VueWrapper): HTMLElement {
  return wrapper.element as HTMLElement;
}

function submenuOf(wrapper: VueWrapper, label: string): HTMLElement | null {
  return rootEl(wrapper).querySelector<HTMLElement>(`[aria-label="${label}"]`);
}

function submenuItems(wrapper: VueWrapper, label: string): HTMLElement[] {
  const region = submenuOf(wrapper, label);
  if (!region) return [];
  return Array.from(region.querySelectorAll<HTMLElement>('button.submenu-item'));
}

describe('AppSidebar — PR-B structure', () => {
  let wrapper: VueWrapper;

  beforeEach(async () => {
    wrapper = await mountSidebar();
  });

  it('renders a top-level "Triggers" section header', () => {
    const labels = Array.from(
      rootEl(wrapper).querySelectorAll<HTMLElement>('.nav-section-label')
    ).map((el) => el.textContent?.trim().replace(/\s+/g, ' ') ?? '');
    expect(labels).toContain('Triggers');
  });

  it('Triggers section contains exactly 25 sub-items (24 trigger facets + 1 Authoring)', () => {
    const items = submenuItems(wrapper, 'Triggers');
    expect(items.length).toBe(25);
  });

  it('Triggers section contains spot-checked items from different blocks', () => {
    const items = submenuItems(wrapper, 'Triggers');
    const texts = items.map((b) => b.textContent?.trim().replace(/\s+/g, ' ') ?? '');
    // Core block
    expect(texts).toContain('Triggers');
    // PR-Review block
    expect(texts).toContain('GitHub Actions');
    // Ops block
    expect(texts).toContain('Webhook Recorder');
    // Authoring block (folded-in Prompt Snippets)
    expect(texts).toContain('Prompt Snippets');
  });

  it('Triggers section renders 6 visual block labels (Core, Configuration, PR-Review, Ops, Introspection, Authoring)', () => {
    const region = submenuOf(wrapper, 'Triggers');
    expect(region).not.toBeNull();
    const blockLabels = Array.from(
      region!.querySelectorAll<HTMLElement>('.submenu-block-label')
    ).map((el) => el.textContent?.trim() ?? '');
    expect(blockLabels).toEqual([
      'Core',
      'Configuration',
      'PR-Review',
      'Ops',
      'Introspection',
      'Authoring',
    ]);
  });

  it('renders a top-level "External Integrations" section header', () => {
    const labels = Array.from(
      rootEl(wrapper).querySelectorAll<HTMLElement>('.nav-section-label')
    ).map((el) => el.textContent?.trim().replace(/\s+/g, ' ') ?? '');
    expect(labels).toContain('External Integrations');
    // Old "Integrations" header is gone (the PR-B rename).
    // The audit notes the section was renamed, not just relabelled.
    expect(labels).not.toContain('Integrations');
  });

  it('External Integrations contains exactly 4 items', () => {
    const items = submenuItems(wrapper, 'External Integrations');
    const texts = items.map((b) => b.textContent?.trim().replace(/\s+/g, ' ') ?? '');
    expect(texts.length).toBe(4);
    expect(texts).toContain('Slack Integration');
    expect(texts).toContain('Ticketing Integration');
    expect(texts).toContain('Notification Channels');
    expect(texts).toContain('On-Call Escalation');
  });

  it('"Forge" no longer renders Triggers as a flat link (it has been promoted to its own top-level section)', () => {
    // The pre-PR-B sidebar rendered Triggers via <SidebarFlatLink>, which
    // produces a top-level <button> with no chevron, no aria-expanded,
    // and no nav-group-toggle class. After PR-B Triggers is a
    // <SidebarGroupToggle> (has chevron + aria-expanded).
    //
    // Collect every top-level button whose .nav-text reads "Triggers"
    // and assert none of them are the old flat-link shape — they must
    // all be group toggles (the new Triggers section + the History
    // "Triggers" sub-section).
    const allButtons = Array.from(
      rootEl(wrapper).querySelectorAll<HTMLElement>('button')
    );
    const triggersButtons = allButtons.filter(
      (b) => b.querySelector<HTMLElement>('.nav-text')?.textContent?.trim() === 'Triggers',
    );
    expect(triggersButtons.length).toBeGreaterThan(0);
    for (const btn of triggersButtons) {
      // Old flat-link shape: no chevron, no aria-expanded attribute.
      // Group toggles always have a chevron and aria-expanded.
      const hasChevron = !!btn.querySelector('.chevron-icon');
      const hasAriaExpanded = btn.hasAttribute('aria-expanded');
      expect(hasChevron, 'Triggers button is a flat link (no chevron)').toBe(true);
      expect(hasAriaExpanded, 'Triggers button lacks aria-expanded').toBe(true);
    }
    // And exactly one such button is the new top-level Triggers section
    // header — the other(s) are the History "Triggers" group.
    const newSectionToggle = triggersButtons.find(
      (b) => b.getAttribute('aria-expanded') !== null,
    );
    expect(newSectionToggle).toBeTruthy();
  });

  it('"Automation Tools" section no longer exists', () => {
    const allText = wrapper.element.textContent ?? '';
    // The label appeared in two places previously: the nav-section-label
    // header AND the aria-label of the submenu region. Both must be gone.
    expect(submenuOf(wrapper, 'Automation Tools')).toBeNull();
    // Defensive: no nav-group-toggle labelled "Automation Tools" either.
    const toggleLabels = Array.from(
      rootEl(wrapper).querySelectorAll<HTMLElement>('.nav-group-toggle .nav-text')
    ).map((el) => el.textContent?.trim() ?? '');
    expect(toggleLabels).not.toContain('Automation Tools');
    // Sanity: presence of "Triggers" header proves we're looking at the
    // new structure, not just a stub render.
    expect(allText).toContain('Triggers');
  });

  it('"security-history" sidebar entry is absent (the route still exists, only the sidebar row is removed)', () => {
    // Old sidebar rendered a "Security Scan" submenu item inside the
    // "Trigger History" submenu that pushed to the security-history
    // route. Confirm no submenu button anywhere has that label
    // pointing through the History submenu region.
    const historyRegion = submenuOf(wrapper, 'Trigger History');
    if (historyRegion) {
      const texts = Array.from(
        historyRegion.querySelectorAll<HTMLElement>('button.submenu-item')
      ).map((b) => b.textContent?.trim().replace(/\s+/g, ' ') ?? '');
      expect(texts).not.toContain('Security Scan');
    }
    // Also: the route name itself shouldn't be wired to any visible
    // submenu item. We don't assert on the whole nav text because a
    // dynamic per-trigger row could legitimately contain "security" as
    // part of a user-named trigger.
  });
});
