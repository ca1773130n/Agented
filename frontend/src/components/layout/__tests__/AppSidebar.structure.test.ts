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
    // PR-D — 4 new lane routes + service-health redirect still resolves
    'dashboards-quality', 'dashboards-cost', 'dashboards-health',
    'dashboards-activity', 'service-health',
    'sketch-chat', 'products', 'product-dashboard', 'product-settings',
    'projects', 'project-dashboard', 'project-settings', 'project-planning',
    'project-instance-playground', 'teams', 'team-dashboard', 'team-settings',
    'agents', 'agent-create',
    'super-agents', 'explore-super-agents',
    'workflows', 'workflow-playground',
    'plugins', 'plugin-design', 'explore-plugins', 'harness-integration',
    'plugin-detail',
    'mcp-servers', 'explore-mcp-servers',
    // PR-C: unified Marketplace replaces 4 Explore X pages + the
    // orphan SkillMarketplace. The old explore-* names still resolve
    // (they redirect to /marketplace?type=X), so keep them registered
    // here for any push-by-name call sites; assertions below verify
    // they no longer appear in the sidebar.
    'marketplace',
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

  it('PR-E: "External Integrations" is no longer a top-level section (folded into System as "Integrations")', () => {
    const labels = Array.from(
      rootEl(wrapper).querySelectorAll<HTMLElement>('.nav-section-label')
    ).map((el) => el.textContent?.trim().replace(/\s+/g, ' ') ?? '');
    // The top-level section header is gone; the items now live as a
    // child group under System.
    expect(labels).not.toContain('External Integrations');
    expect(labels).not.toContain('Integrations');
  });

  it('PR-E: Integrations group exists under System with the original 3 items', () => {
    // The renamed-to-"Integrations" group still carries the same 3
    // items it had as "External Integrations" before PR-E.
    const items = submenuItems(wrapper, 'Integrations');
    const texts = items.map((b) => b.textContent?.trim().replace(/\s+/g, ' ') ?? '');
    expect(texts.length).toBe(3);
    expect(texts).toContain('Slack Notifications');
    expect(texts).toContain('Jira / Linear');
    expect(texts).toContain('Notification Channels');
    expect(texts).not.toContain('On-Call Escalation');
    // And the old aria-label/region is gone.
    expect(submenuOf(wrapper, 'External Integrations')).toBeNull();
  });

  it('PR-D: Dashboards submenu collapses to exactly 5 items (1 landing + 4 lanes)', () => {
    const items = submenuItems(wrapper, 'Dashboards');
    const texts = items.map((b) => b.textContent?.trim().replace(/\s+/g, ' ') ?? '');
    expect(texts.length).toBe(5);
    expect(texts).toEqual([
      'All Dashboards',
      'Quality',
      'Cost',
      'Health',
      'Activity',
    ]);
    // None of the per-dashboard items remain.
    for (const stale of ['Security Scan', 'PR Review', 'Token Usage', 'Scheduling',
                          'Analytics', 'Health Monitor', 'Bot Health', 'Impact Report',
                          'Cross-Team Insights', 'Execution Queue', 'Anomaly Detection',
                          'ROI Leaderboard']) {
      expect(texts).not.toContain(stale);
    }
  });

  it('PR-D: Scheduling is a flat top-level link (no expandable section)', () => {
    const allButtons = Array.from(
      rootEl(wrapper).querySelectorAll<HTMLElement>('button'),
    );
    const schedulingButtons = allButtons.filter(
      (b) => b.querySelector<HTMLElement>('.nav-text')?.textContent?.trim() === 'Scheduling',
    );
    expect(schedulingButtons.length).toBe(1);
    const btn = schedulingButtons[0];
    // Flat link shape: no chevron, no aria-expanded.
    expect(btn.querySelector('.chevron-icon')).toBeNull();
    expect(btn.hasAttribute('aria-expanded')).toBe(false);
    // No submenu region was rendered for Scheduling.
    expect(submenuOf(wrapper, 'Scheduling')).toBeNull();
  });

  it('PR-D: Platform sidebar no longer contains team-leaderboard', () => {
    // Platform's submenu may exist or not depending on what's labelled;
    // assert no top-level submenu button anywhere reads "ROI Leaderboard"
    // or is wired to the team-leaderboard route.
    const allSubmenuItems = Array.from(
      rootEl(wrapper).querySelectorAll<HTMLElement>('button.submenu-item'),
    ).map((b) => b.textContent?.trim().replace(/\s+/g, ' ') ?? '');
    expect(allSubmenuItems).not.toContain('ROI Leaderboard');
    // Belt-and-suspenders: Team Leaderboard is the legacy label.
    expect(allSubmenuItems).not.toContain('Team Leaderboard');
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

  it('PR-C: Forge no longer renders the 4 "Explore X" submenu items (they live under the unified Marketplace now)', () => {
    // Skills submenu: no "Explore" row.
    const skillsTexts = submenuItems(wrapper, 'Skills').map(
      (b) => b.textContent?.trim().replace(/\s+/g, ' ') ?? '',
    );
    expect(skillsTexts).not.toContain('Explore');

    // Plugins submenu: no "Explore" row (the dynamic per-plugin items
    // are user-named so we can't blanket-assert on those).
    const pluginsRegion = submenuOf(wrapper, 'Plugins');
    expect(pluginsRegion).not.toBeNull();
    const pluginsStaticTexts = Array.from(
      pluginsRegion!.querySelectorAll<HTMLElement>('button.submenu-item'),
    )
      .map((b) => b.textContent?.trim().replace(/\s+/g, ' ') ?? '')
      .filter((t) =>
        ['All Plugins', 'Design a Plugin', 'Explore', 'Harness Integration'].includes(t),
      );
    expect(pluginsStaticTexts).not.toContain('Explore');

    // MCPs submenu: no "Explore" row. (PR-E renamed "MCP Servers" → "MCPs".)
    const mcpTexts = submenuItems(wrapper, 'MCPs').map(
      (b) => b.textContent?.trim().replace(/\s+/g, ' ') ?? '',
    );
    expect(mcpTexts).not.toContain('Explore');

    // SuperAgents submenu: no "Explore" row.
    const saTexts = submenuItems(wrapper, 'SuperAgents').map(
      (b) => b.textContent?.trim().replace(/\s+/g, ' ') ?? '',
    );
    expect(saTexts).not.toContain('Explore');
  });

  it('PR-E: Marketplace is a top-level peer (no longer nested inside Forge)', () => {
    // The Marketplace entry is a flat link (no chevron, no
    // aria-expanded). PR-E promoted it out of Forge to its own slot
    // between Forge and Triggers.
    const allButtons = Array.from(
      rootEl(wrapper).querySelectorAll<HTMLElement>('button'),
    );
    const marketplaceButtons = allButtons.filter(
      (b) =>
        b.querySelector<HTMLElement>('.nav-text')?.textContent?.trim() ===
        'Marketplace',
    );
    expect(marketplaceButtons.length).toBe(1);
    const btn = marketplaceButtons[0];
    expect(btn.querySelector('.chevron-icon')).toBeNull();
    expect(btn.hasAttribute('aria-expanded')).toBe(false);
  });

  it('PR-E: "MCPs" label replaces "MCP Servers" on the sidebar group toggle', () => {
    const toggleLabels = Array.from(
      rootEl(wrapper).querySelectorAll<HTMLElement>('.nav-group-toggle .nav-text')
    ).map((el) => el.textContent?.trim() ?? '');
    expect(toggleLabels).toContain('MCPs');
    expect(toggleLabels).not.toContain('MCP Servers');
    // The submenu region's aria-label also changes.
    expect(submenuOf(wrapper, 'MCPs')).not.toBeNull();
    expect(submenuOf(wrapper, 'MCP Servers')).toBeNull();
  });

  it('PR-E: Dashboards group lives inside the Work group (no top-level slot above Work)', () => {
    // Dashboards is now an expandable group rendered after Sketch inside
    // the Work section. The Dashboards submenu region must still exist
    // (its body is unchanged from PR-D) — only its position moved.
    expect(submenuOf(wrapper, 'Dashboards')).not.toBeNull();
  });

  it('PR-E: Scheduling flat link is rendered inside the Work group (after Dashboards)', () => {
    // Order check: Sketch → Dashboards → Scheduling among the buttons
    // appearing before the Organization section label.
    const all = Array.from(rootEl(wrapper).children[0].children) as HTMLElement[];
    // Find indexes of the Work label, the Organization label, and the
    // three Work entries by their .nav-text content.
    function indexOfLabelText(text: string): number {
      return all.findIndex(
        (el) =>
          el.classList.contains('nav-section-label') &&
          el.textContent?.trim() === text,
      );
    }
    function indexOfButtonText(text: string): number {
      return all.findIndex(
        (el) =>
          el.tagName === 'BUTTON' &&
          el.querySelector<HTMLElement>('.nav-text')?.textContent?.trim() === text,
      );
    }
    const workIdx = indexOfLabelText('Work');
    const orgIdx = indexOfLabelText('Organization');
    const sketchIdx = indexOfButtonText('Sketch');
    const dashIdx = indexOfButtonText('Dashboards');
    const schedIdx = indexOfButtonText('Scheduling');
    expect(workIdx).toBeGreaterThan(-1);
    expect(orgIdx).toBeGreaterThan(workIdx);
    // All three Work entries sit between Work label and Organization label.
    expect(sketchIdx).toBeGreaterThan(workIdx);
    expect(sketchIdx).toBeLessThan(orgIdx);
    expect(dashIdx).toBeGreaterThan(sketchIdx);
    expect(dashIdx).toBeLessThan(orgIdx);
    expect(schedIdx).toBeGreaterThan(dashIdx);
    expect(schedIdx).toBeLessThan(orgIdx);
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
