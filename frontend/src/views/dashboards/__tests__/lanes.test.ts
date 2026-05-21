/**
 * PR-D — Smoke test per lane page.
 * Each lane mounts and renders the expected card subcomponents.
 * Cards stub their internal data fetching via API mocks so the test
 * doesn't try to hit /admin/* endpoints.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import { defineComponent, h } from 'vue';

vi.mock('../../../services/api', () => {
  const empty = async () => ({});
  return {
    ApiError: class ApiError extends Error { status = 0; },
    auditApi: {
      getStats: vi.fn().mockResolvedValue({ current: { total_findings: 0, status: 'pass', severity_totals: {} }, historical: { total_audits: 0, total_findings: 0, severity_totals: {} }, projects: [] }),
      getProjects: vi.fn().mockResolvedValue({ projects: [] }),
      getHistory: vi.fn().mockResolvedValue({ audits: [] }),
    },
    triggerApi: {
      list: vi.fn().mockResolvedValue({ triggers: [] }),
      setAutoResolve: vi.fn().mockResolvedValue({}),
      run: vi.fn().mockResolvedValue({}),
    },
    prReviewApi: {
      getStats: vi.fn().mockResolvedValue({ open_prs: 0, total_prs: 0 }),
      list: vi.fn().mockResolvedValue({ reviews: [], total: 0 }),
      getHistory: vi.fn().mockResolvedValue({ history: [] }),
    },
    analyticsApi: {
      getExecutionAnalytics: vi.fn().mockResolvedValue({ data_points: [] }),
      getBotEffectiveness: vi.fn().mockResolvedValue({ bots: [] }),
      getHealth: vi.fn().mockResolvedValue({ status: 'ok', alerts: [] }),
    },
    botHealthApi: { listRollups: vi.fn().mockResolvedValue({ rollups: [] }) },
    monitoringApi: {
      getStatus: vi.fn().mockResolvedValue({ enabled: false, windows: [], polling_minutes: 0 }),
      getHistory: vi.fn().mockResolvedValue({ snapshots: [] }),
      pollNow: vi.fn().mockResolvedValue({ windows: [] }),
    },
    budgetApi: {
      getUsageSummary: vi.fn().mockResolvedValue({ summary: [] }),
      getUsageByEntity: vi.fn().mockResolvedValue({ entities: [] }),
      getLimits: vi.fn().mockResolvedValue({ limits: [] }),
      getSessionStats: vi.fn().mockResolvedValue({ stats: null }),
      getAllTimeSpend: vi.fn().mockResolvedValue({ total_cost_usd: 0 }),
      collectSessions: vi.fn().mockResolvedValue({}),
      deleteLimit: vi.fn().mockResolvedValue({}),
    },
    schedulerApi: { getStatus: vi.fn().mockResolvedValue({ sessions: [], global_summary: { queued: 0, running: 0, stopped: 0 } }) },
    rotationApi: {
      getStatus: vi.fn().mockResolvedValue({ sessions: [], evaluator: { evaluation_interval_seconds: 0, hysteresis_threshold: 0, active_evaluations: 0, evaluation_states: {} } }),
      getHistory: vi.fn().mockResolvedValue({ events: [] }),
    },
    executionApi: { list: vi.fn().mockResolvedValue({ executions: [] }), cancel: vi.fn().mockResolvedValue({}) },
    agentApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
    teamApi: { list: vi.fn().mockResolvedValue({ teams: [] }) },
    productApi: { list: vi.fn().mockResolvedValue({ products: [] }) },
    projectApi: { list: vi.fn().mockResolvedValue({ projects: [] }) },
    serviceHealthApi: { list: vi.fn().mockResolvedValue({ accounts: [] }) },
    crossTeamApi: empty,
    impactReportApi: empty,
    roiApi: empty,
  };
});

vi.mock('../../../composables/useWebMcpTool', () => ({
  useWebMcpTool: vi.fn(),
}));

vi.mock('../../../composables/useToast', () => ({
  useToast: () => vi.fn(),
}));

// vi.mock factories are hoisted — they can't reference outer variables.
// Inline the stub fully in each factory.
vi.mock('../../../components/security/FindingsChart.vue', () => ({ default: { name: 'StubFindings', render: () => null } }));
vi.mock('../../../components/security/PrHistoryChart.vue', () => ({ default: { name: 'StubPrHistory', render: () => null } }));
vi.mock('../../../components/security/RunScanModal.vue', () => ({ default: { name: 'StubRunScan', render: () => null } }));
vi.mock('../../../components/security/ResolveIssuesModal.vue', () => ({ default: { name: 'StubResolve', render: () => null } }));
vi.mock('../../../components/monitoring/RotationTimelineChart.vue', () => ({ default: { name: 'StubRotChart', render: () => null } }));
vi.mock('../../../components/monitoring/TokenUsageChart.vue', () => ({ default: { name: 'StubTokenChart', render: () => null } }));
vi.mock('../../../components/monitoring/BudgetLimitForm.vue', () => ({ default: { name: 'StubBudgetForm', render: () => null } }));
vi.mock('../../../components/monitoring/TokenBreakdownCard.vue', () => ({ default: { name: 'StubTokenBreakdown', render: () => null } }));
vi.mock('../../../components/monitoring/MonitoringSection.vue', () => ({ default: { name: 'StubMonitoring', render: () => null } }));
vi.mock('../../../components/monitoring/EntitySpendSection.vue', () => ({ default: { name: 'StubEntitySpend', render: () => null } }));
vi.mock('../../../components/monitoring/BudgetLimitsSection.vue', () => ({ default: { name: 'StubBudgetLimits', render: () => null } }));
vi.mock('../../../components/credentials/CredentialStatusBanner.vue', () => ({ default: { name: 'StubCredBanner', render: () => null } }));

import QualityPage from '../QualityPage.vue';
import CostPage from '../CostPage.vue';
import HealthPage from '../HealthPage.vue';
import ActivityPage from '../ActivityPage.vue';

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: defineComponent({ render: () => h('div') }) },
      { path: '/dashboards/quality', name: 'dashboards-quality', component: QualityPage },
      { path: '/dashboards/cost', name: 'dashboards-cost', component: CostPage },
      { path: '/dashboards/health', name: 'dashboards-health', component: HealthPage },
      { path: '/dashboards/activity', name: 'dashboards-activity', component: ActivityPage },
      { path: '/trigger/:triggerId', name: 'trigger-dashboard', component: defineComponent({ render: () => h('div') }) },
      { path: '/security-history', name: 'security-history', component: defineComponent({ render: () => h('div') }) },
      { path: '/audit/:auditId', name: 'audit-detail', component: defineComponent({ render: () => h('div') }) },
      // Router-links inside ROI/CrossTeam cards point at team-dashboard
      // / project-dashboard / agent-detail for drill-downs. Register
      // minimal stubs so vue-router doesn't fire "No match" warnings
      // during the smoke mount.
      { path: '/teams/:teamId', name: 'team-dashboard', component: defineComponent({ render: () => h('div') }) },
      { path: '/projects/:projectId', name: 'project-dashboard', component: defineComponent({ render: () => h('div') }) },
      { path: '/agents/:agentId', name: 'agent-detail', component: defineComponent({ render: () => h('div') }) },
    ],
  });
}

async function mountLane(component: any) {
  const router = buildRouter();
  await router.push({ path: '/' });
  await router.isReady();
  const wrapper = mount(component, { global: { plugins: [router] }, attachTo: document.body });
  await flushPromises();
  return wrapper;
}

describe('PR-D lane pages — smoke', () => {
  beforeEach(() => {
    // Remove any leftover attached nodes between tests.
    while (document.body.firstChild) {
      document.body.removeChild(document.body.firstChild);
    }
  });

  it('QualityPage mounts and renders security + pr-review + anomaly card anchors', async () => {
    const w = await mountLane(QualityPage);
    expect(w.find('#security').exists()).toBe(true);
    expect(w.find('#pr-review').exists()).toBe(true);
    expect(w.find('#anomaly-detection').exists()).toBe(true);
  });

  it('CostPage mounts and renders the token-usage anchor', async () => {
    const w = await mountLane(CostPage);
    expect(w.find('#token-usage').exists()).toBe(true);
  });

  it('HealthPage mounts and renders all 4 health anchors', async () => {
    const w = await mountLane(HealthPage);
    expect(w.find('#health-monitor').exists()).toBe(true);
    expect(w.find('#bot-health').exists()).toBe(true);
    expect(w.find('#service-health').exists()).toBe(true);
    expect(w.find('#bot-effectiveness').exists()).toBe(true);
  });

  it('ActivityPage mounts and renders the 7 activity anchors (2 visual blocks)', async () => {
    const w = await mountLane(ActivityPage);
    expect(w.find('#scheduling').exists()).toBe(true);
    expect(w.find('#execution-queue').exists()).toBe(true);
    expect(w.find('#execution-volume').exists()).toBe(true);
    expect(w.find('#success-rate').exists()).toBe(true);
    expect(w.find('#impact-report').exists()).toBe(true);
    expect(w.find('#cross-team-insights').exists()).toBe(true);
    expect(w.find('#roi-leaderboard').exists()).toBe(true);
    expect(w.findAll('.lane-block__title').map((n) => n.text())).toEqual(['Live ops', 'Reports']);
  });
});
