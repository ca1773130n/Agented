import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises, VueWrapper } from '@vue/test-utils';
import { ref, computed, inject, defineComponent } from 'vue';
import { createRouter, createMemoryHistory, type Router } from 'vue-router';
import App from '../../App.vue';

// ── Shared mock fns (captured so tests can assert on them) ─────────────────

const mockStartPolling = vi.fn();
const mockStopPolling = vi.fn();
const mockLoadSidebarData = vi.fn();
const mockRetrySidebarSection = vi.fn();
const mockRefreshTriggers = vi.fn();
const mockLoadPlugins = vi.fn();
const mockRegisterGenericTools = vi.fn();
const mockStartTour = vi.fn();
const mockNextStep = vi.fn();
const mockSkipStep = vi.fn();

// ── Mocks ──────────────────────────────────────────────────────────────────

vi.mock('../../services/api', () => ({
  setupApi: { bundleInstall: vi.fn().mockResolvedValue({ status: 'already_installed' }) },
  healthApi: {
    authStatus: vi.fn().mockResolvedValue({ auth_required: false, authenticated: false }),
  },
  getApiKey: vi.fn().mockReturnValue(null),
}));

vi.mock('../../composables/useTour', () => ({
  useTour: () => ({
    active: ref(false),
    currentStepIndex: ref(0),
    currentStep: computed(() => null),
    completed: ref([]),
    totalSteps: 8,
    displayStepNumber: computed(() => 1),
    tourComplete: ref(false),
    startTour: mockStartTour,
    nextStep: mockNextStep,
    skipStep: mockSkipStep,
    endTour: vi.fn(),
    updateStepRoute: vi.fn(),
    steps: [],
  }),
}));

vi.mock('../../components/tour/TourOverlay.vue', () => ({
  default: defineComponent({
    name: 'TourOverlay',
    props: ['active', 'step', 'stepNumber', 'totalSteps'],
    emits: ['next', 'skip'],
    template: '<div data-testid="tour-overlay" v-if="active">Tour</div>',
  }),
}));

vi.mock('../../webmcp/generic-tools', () => ({
  registerGenericTools: (...args: unknown[]) => mockRegisterGenericTools(...args),
}));

vi.mock('../../composables/useSidebarCollapse', () => ({
  useSidebarCollapse: () => ({
    isCollapsed: ref(false),
    isMobileOpen: ref(false),
    isMobile: computed(() => false),
    toggleCollapse: vi.fn(),
    toggleMobile: vi.fn(),
    closeMobile: vi.fn(),
  }),
}));

vi.mock('../../composables/useSidebarData', () => ({
  useSidebarData: () => ({
    customTriggers: ref([]),
    products: ref([]),
    projects: ref([]),
    teams: ref([]),
    plugins: ref([]),
    sidebarBackends: ref([]),
    appVersion: ref('1.0.0-test'),
    sidebarLoading: ref(false),
    sidebarErrors: ref({}),
    loadSidebarData: mockLoadSidebarData,
    retrySidebarSection: mockRetrySidebarSection,
    refreshTriggers: mockRefreshTriggers,
    loadPlugins: mockLoadPlugins,
  }),
}));

vi.mock('../../composables/useHealthPolling', () => ({
  useHealthPolling: () => ({
    activeExecutionCount: ref(0),
    healthColor: ref('#00ff88'),
    healthTooltip: ref('Healthy'),
    startPolling: mockStartPolling,
    stopPolling: mockStopPolling,
  }),
}));

vi.mock('../../components/layout/AppSidebar.vue', () => ({
  default: defineComponent({
    name: 'AppSidebar',
    props: [
      'appVersion',
      'healthColor',
      'healthTooltip',
      'activeExecutionCount',
      'customTriggers',
      'products',
      'projects',
      'teams',
      'plugins',
      'sidebarBackends',
      'collapsed',
      'isMobile',
      'mobileOpen',
      'sidebarLoading',
      'sidebarErrors',
    ],
    template: '<aside class="sidebar" data-testid="app-sidebar">Sidebar</aside>',
  }),
}));

vi.mock('../../components/base/ErrorBoundary.vue', () => ({
  default: defineComponent({
    name: 'ErrorBoundary',
    template: '<div class="error-boundary"><slot /></div>',
  }),
}));

vi.mock('../../components/layout/AppHeader.vue', () => ({
  default: defineComponent({
    name: 'AppHeader',
    emits: ['toggleSidebar'],
    template: '<header class="app-header" data-testid="app-header">Header</header>',
  }),
}));

// ── Helpers ────────────────────────────────────────────────────────────────

function createTestRouter(meta: Record<string, unknown> = {}): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/',
        name: 'home',
        component: defineComponent({ template: '<div>Home</div>' }),
        meta,
      },
    ],
  });
}

async function mountApp(routeMeta: Record<string, unknown> = {}): Promise<VueWrapper> {
  const router = createTestRouter(routeMeta);
  router.push('/');
  await router.isReady();

  const wrapper = mount(App, {
    global: {
      plugins: [router],
    },
  });
  await flushPromises();
  return wrapper;
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('App.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders without errors', async () => {
    const wrapper = await mountApp();
    expect(wrapper.exists()).toBe(true);
  });

  it('renders the app-layout container', async () => {
    const wrapper = await mountApp();
    expect(wrapper.find('.app-layout').exists()).toBe(true);
  });

  it('renders the AppSidebar component', async () => {
    const wrapper = await mountApp();
    expect(wrapper.find('[data-testid="app-sidebar"]').exists()).toBe(true);
  });

  it('renders the main content area with correct id', async () => {
    const wrapper = await mountApp();
    const main = wrapper.find('#main-content');
    expect(main.exists()).toBe(true);
    expect(main.element.tagName).toBe('MAIN');
  });

  it('renders router-view inside ErrorBoundary', async () => {
    const wrapper = await mountApp();
    const errorBoundary = wrapper.find('.error-boundary');
    expect(errorBoundary.exists()).toBe(true);
    // The router-view renders the "Home" component inside the error boundary
    expect(errorBoundary.text()).toContain('Home');
  });

  it('renders the skip-to-content accessibility link', async () => {
    const wrapper = await mountApp();
    const skipLink = wrapper.find('.skip-to-content');
    expect(skipLink.exists()).toBe(true);
    expect(skipLink.attributes('href')).toBe('#main-content');
    expect(skipLink.text()).toBe('Skip to content');
  });

  it('renders the collapse toggle button on desktop', async () => {
    const wrapper = await mountApp();
    const collapseBtn = wrapper.find('.collapse-toggle');
    expect(collapseBtn.exists()).toBe(true);
  });

  it('renders toast container via Teleport', async () => {
    await mountApp();
    // Teleported content ends up in document.body in happy-dom
    const toastContainer = document.querySelector('.toast-container');
    expect(toastContainer).not.toBeNull();
    expect(toastContainer?.getAttribute('role')).toBe('status');
    expect(toastContainer?.getAttribute('aria-live')).toBe('polite');
  });

  it('does not apply full-bleed class by default', async () => {
    const wrapper = await mountApp();
    const contentWrapper = wrapper.find('.content-wrapper');
    expect(contentWrapper.exists()).toBe(true);
    expect(contentWrapper.classes()).not.toContain('full-bleed');
  });

  it('applies full-bleed class when route meta has fullBleed', async () => {
    const wrapper = await mountApp({ fullBleed: true });
    const contentWrapper = wrapper.find('.content-wrapper');
    expect(contentWrapper.classes()).toContain('full-bleed');
  });

  it('passes appVersion prop to AppSidebar', async () => {
    const wrapper = await mountApp();
    const sidebar = wrapper.findComponent({ name: 'AppSidebar' });
    expect(sidebar.props('appVersion')).toBe('1.0.0-test');
  });

  it('passes health props to AppSidebar', async () => {
    const wrapper = await mountApp();
    const sidebar = wrapper.findComponent({ name: 'AppSidebar' });
    expect(sidebar.props('healthColor')).toBe('#00ff88');
    expect(sidebar.props('healthTooltip')).toBe('Healthy');
    expect(sidebar.props('activeExecutionCount')).toBe(0);
  });
});

describe('App.vue toast provide/inject', () => {
  it('provides showToast function to child components', async () => {
    let injectedToast: unknown = null;

    const ChildComponent = defineComponent({
      setup() {
        injectedToast = inject('showToast');
        return {};
      },
      template: '<div>Child</div>',
    });

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: ChildComponent },
      ],
    });

    router.push('/');
    await router.isReady();

    mount(App, {
      global: { plugins: [router] },
    });

    expect(typeof injectedToast).toBe('function');
  });

  it('provides retrySidebarSection function to child components', async () => {
    let injectedRetry: unknown = null;

    const ChildComponent = defineComponent({
      setup() {
        injectedRetry = inject('retrySidebarSection');
        return {};
      },
      template: '<div>Child</div>',
    });

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: ChildComponent },
      ],
    });

    router.push('/');
    await router.isReady();

    mount(App, {
      global: { plugins: [router] },
    });

    expect(typeof injectedRetry).toBe('function');
  });

  it('provides refreshTriggers function to child components', async () => {
    let injectedRefresh: unknown = null;

    const ChildComponent = defineComponent({
      setup() {
        injectedRefresh = inject('refreshTriggers');
        return {};
      },
      template: '<div>Child</div>',
    });

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: ChildComponent },
      ],
    });

    router.push('/');
    await router.isReady();

    mount(App, {
      global: { plugins: [router] },
    });

    expect(typeof injectedRefresh).toBe('function');
  });
});

describe('App.vue calls lifecycle hooks', () => {
  it('calls registerGenericTools on setup', async () => {
    await mountApp();
    expect(mockRegisterGenericTools).toHaveBeenCalled();
  });

  it('calls startPolling on mount with 10s interval', async () => {
    await mountApp();
    expect(mockStartPolling).toHaveBeenCalledWith(10000);
  });

  it('calls loadSidebarData on mount', async () => {
    await mountApp();
    expect(mockLoadSidebarData).toHaveBeenCalled();
  });
});
