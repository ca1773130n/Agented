import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import {
  createRouter,
  createMemoryHistory,
  type Router,
} from 'vue-router';
import { defineComponent, h } from 'vue';
import MarketplacePage from '../MarketplacePage.vue';

// Stub the API surface used by the per-type subcomponents — every tab
// mounts its own component on switch and hits one of these. We resolve
// to empty result sets so the components render their empty-state
// markup without churning through additional data branches.
vi.mock('../../services/api', () => ({
  marketplaceApi: {
    search: vi.fn().mockResolvedValue({ results: [] }),
    list: vi.fn().mockResolvedValue({ marketplaces: [] }),
    refreshCache: vi.fn().mockResolvedValue({}),
    create: vi.fn(),
    delete: vi.fn(),
  },
  skillsShApi: {
    search: vi
      .fn()
      .mockResolvedValue({ results: [], npx_available: true }),
    install: vi.fn(),
  },
  userSkillsApi: { add: vi.fn() },
  pluginExportApi: { importFromMarketplace: vi.fn() },
  mcpServerApi: { create: vi.fn() },
  ApiError: class extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
}));

// The subcomponents register webmcp tools on mount; stub the hook so
// the registry stays clean across mounts.
vi.mock('../../composables/useWebMcpTool', () => ({
  useWebMcpTool: () => ({}),
}));

// Focus trap touches DOM event listeners we don't care about here.
vi.mock('../../composables/useFocusTrap', () => ({
  useFocusTrap: () => ({}),
}));

// Toast composable: provide a no-op so injection doesn't fail.
vi.mock('../../composables/useToast', () => ({
  useToast: () => () => undefined,
}));

const StubView = defineComponent({
  name: 'StubView',
  render: () => h('div'),
});

function buildRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/marketplace',
        name: 'marketplace',
        component: MarketplacePage,
      },
      { path: '/settings', name: 'settings', component: StubView },
    ],
  });
}

async function mountAt(query: Record<string, string> = {}): Promise<{
  wrapper: VueWrapper;
  router: Router;
}> {
  const router = buildRouter();
  await router.push({ name: 'marketplace', query });
  await router.isReady();
  const wrapper = mount(MarketplacePage, {
    global: {
      plugins: [router],
      stubs: {
        // The detail panels use <Teleport>; stub it so children render
        // inline and we don't have to chase them around the DOM.
        Teleport: true,
        PageHeader: true,
      },
    },
  });
  await flushPromises();
  return { wrapper, router };
}

describe('MarketplacePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('defaults to the Plugins tab when no ?type query param is given', async () => {
    const { wrapper } = await mountAt();
    expect(wrapper.findComponent({ name: 'MarketplacePlugins' }).exists()).toBe(
      true,
    );
    expect(wrapper.findComponent({ name: 'MarketplaceSkills' }).exists()).toBe(
      false,
    );
  });

  it('renders MarketplaceSkills when ?type=skills', async () => {
    const { wrapper } = await mountAt({ type: 'skills' });
    expect(wrapper.findComponent({ name: 'MarketplaceSkills' }).exists()).toBe(
      true,
    );
    expect(wrapper.findComponent({ name: 'MarketplacePlugins' }).exists()).toBe(
      false,
    );
  });

  it('renders MarketplaceMcpServers when ?type=mcp-servers', async () => {
    const { wrapper } = await mountAt({ type: 'mcp-servers' });
    expect(
      wrapper.findComponent({ name: 'MarketplaceMcpServers' }).exists(),
    ).toBe(true);
  });

  it('renders MarketplaceSuperAgents when ?type=super-agents', async () => {
    const { wrapper } = await mountAt({ type: 'super-agents' });
    expect(
      wrapper.findComponent({ name: 'MarketplaceSuperAgents' }).exists(),
    ).toBe(true);
  });

  it('falls back to Plugins tab on an unknown ?type value', async () => {
    const { wrapper } = await mountAt({ type: 'bogus' });
    expect(wrapper.findComponent({ name: 'MarketplacePlugins' }).exists()).toBe(
      true,
    );
  });

  it('clicking a tab updates the URL query param and swaps the rendered subcomponent', async () => {
    const { wrapper, router } = await mountAt();
    const tabs = wrapper.findAll('.tab-btn');
    expect(tabs.length).toBe(4);

    // Click the Skills tab (index 1) and let router.replace settle.
    await tabs[1].trigger('click');
    await flushPromises();

    expect(router.currentRoute.value.query.type).toBe('skills');
    expect(wrapper.findComponent({ name: 'MarketplaceSkills' }).exists()).toBe(
      true,
    );
    expect(wrapper.findComponent({ name: 'MarketplacePlugins' }).exists()).toBe(
      false,
    );
  });

  it('renders all four tab buttons in the strip', async () => {
    const { wrapper } = await mountAt();
    const labels = wrapper
      .findAll('.tab-btn')
      .map((b) => b.text().trim());
    expect(labels).toEqual(['Plugins', 'Skills', 'MCP Servers', 'SuperAgents']);
  });
});
