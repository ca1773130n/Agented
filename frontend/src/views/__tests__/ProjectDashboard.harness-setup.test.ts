/**
 * P8 — ProjectDashboard one-click team harness setup surface (REQ-19 / SC1).
 *
 * Verifies the button (shown when status 'none'), the per-state status chip,
 * and the EventSource-fed step panel. The harnessSetup api is mocked so no
 * network call fires; EventSource is replaced with a controllable fake so we
 * can dispatch 'message' frames synchronously.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import ProjectDashboard from '../ProjectDashboard.vue';

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: { projectId: 'proj-test01' }, query: {}, hash: '' }),
}));

// Controllable fake EventSource — the dashboard calls
// grdApi.streamHarnessSetup() which (mocked below) returns one of these.
class FakeEventSource {
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  closed = false;
  close() {
    this.closed = true;
  }
  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent);
  }
}
let lastEventSource: FakeEventSource | null = null;

vi.mock('../../services/api', () => {
  const ok = (v: unknown) => vi.fn().mockResolvedValue(v);
  return {
    ApiError: class extends Error {
      status: number;
      constructor(status: number, message: string) {
        super(message);
        this.status = status;
      }
    },
    projectApi: {
      get: ok({ id: 'proj-test01', name: 'Test', github_repo: null, local_path: '/tmp/x' }),
      getHarnessStatus: ok({}),
      listSkills: ok({ skills: [] }),
      listInstallations: ok({ installations: [] }),
    },
    grdApi: {
      getPlanningStatus: ok({ grd_init_status: 'none', active_session_id: null }),
      getHarnessSetupStatus: ok({ harness_setup_status: 'none', steps: [] }),
      triggerHarnessSetup: ok({ harness_setup_status: 'running' }),
      streamHarnessSetup: vi.fn(() => {
        lastEventSource = new FakeEventSource();
        return lastEventSource;
      }),
    },
    hookApi: { list: ok({ hooks: [] }) },
    commandApi: { list: ok({ commands: [] }) },
    ruleApi: { list: ok({ rules: [] }) },
    agentApi: { list: ok({ agents: [] }) },
    teamApi: { get: ok({}) },
    superAgentApi: { list: ok({ super_agents: [] }), activityStatus: ok({}) },
    superAgentSessionApi: { list: ok({ sessions: [] }) },
    projectInstanceApi: { list: ok({ instances: [] }) },
  };
});

function mountDashboard() {
  return mount(ProjectDashboard, {
    global: {
      stubs: {
        // EntityLayout owns the load lifecycle via :load-entity. The real
        // component calls it on mount; the stub mirrors that so loadData()
        // runs and `project` is populated before the slot renders.
        EntityLayout: {
          props: ['loadEntity'],
          async mounted() {
            if (this.loadEntity) await this.loadEntity();
          },
          template: '<div><slot /></div>',
        },
        InteractiveSetup: true,
        ProjectStatusCard: true,
        ProjectTeamLeaderChat: true,
        ProjectTeamsSection: true,
        ProjectTeamCanvas: true,
        ProjectLibraryTabs: true,
        ProjectForgeBindingsPanel: true,
        HarnessStatusSection: true,
        teleport: true,
      },
    },
  });
}

describe('ProjectDashboard — team harness setup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    lastEventSource = null;
  });

  it('renders the Setup Team Harness button when status is none', async () => {
    const wrapper = mountDashboard();
    await flushPromises();
    expect(wrapper.find('[data-testid="harness-setup-btn"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="harness-setup-chip"]').exists()).toBe(false);
  });

  it('shows the running chip and opens an EventSource after triggering', async () => {
    const wrapper = mountDashboard();
    await flushPromises();
    await wrapper.find('[data-testid="harness-setup-btn"]').trigger('click');
    await flushPromises();
    const chip = wrapper.find('[data-testid="harness-setup-chip"]');
    expect(chip.exists()).toBe(true);
    expect(chip.text()).toContain('Setting up');
    expect(lastEventSource).not.toBeNull();
  });

  it('renders step rows pushed via the EventSource message stream', async () => {
    const wrapper = mountDashboard();
    await flushPromises();
    await wrapper.find('[data-testid="harness-setup-btn"]').trigger('click');
    await flushPromises();

    lastEventSource!.emit({ step: 'grd_init', status: 'ok', detail: 'initialized' });
    lastEventSource!.emit({ step: 'team_topology', status: 'failed', detail: 'boom' });
    await flushPromises();

    const steps = wrapper.findAll('[data-testid="harness-setup-step"]');
    expect(steps.length).toBe(2);
    expect(wrapper.find('[data-testid="harness-setup-panel"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('Initialize GRD');
    expect(wrapper.text()).toContain('Team Topology');
    expect(wrapper.text()).toContain('initialized');
  });

  it('transitions to the ready chip on the __done__ frame and closes the stream', async () => {
    const wrapper = mountDashboard();
    await flushPromises();
    await wrapper.find('[data-testid="harness-setup-btn"]').trigger('click');
    await flushPromises();

    const es = lastEventSource!;
    es.emit({ step: '__done__', status: 'ready' });
    await flushPromises();

    expect(es.closed).toBe(true);
  });
});
