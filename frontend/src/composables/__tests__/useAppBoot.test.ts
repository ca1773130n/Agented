/**
 * v0.7.6: Codex follow-up coverage for useAppBoot.
 *
 * Pre-existing App.test.ts never exercised the `?tour=start` query-param
 * watcher branch — Codex flagged this as uncovered. These tests run the
 * composable inside a host component, drive the route's query, and assert
 * the watcher's three behaviors:
 *
 *   1. With `tour=start`, the composable starts the tour and clears the query.
 *   2. With no `tour` query, beginTour is NOT called.
 *   3. The query param is removed via `router.replace({ query: {} })`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { defineComponent, h, ref, type Ref } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';

// ── Mocks ─────────────────────────────────────────────────────────────────

// Mutable route shape so individual tests can drive the watcher.
const routeQuery = ref<{ tour?: string }>({});
const routeFullPath = ref('/login');

const replaceMock = vi.fn();
const pushMock = vi.fn();

vi.mock('vue-router', () => ({
  useRoute: () => ({
    get query() {
      return routeQuery.value;
    },
    get fullPath() {
      return routeFullPath.value;
    },
  }),
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
  }),
}));

// getApiKey (from the api client) — drives the "hide the stale banner at once
// when a key is already present" branch of the navigation watcher.
const getApiKeyReturn = ref<string | null>(null);
vi.mock('../../services/api/client', () => ({
  getApiKey: () => getApiKeyReturn.value,
}));

// Health API: pretend the user is fully authenticated to skip the
// banner/redirect branches and let onMounted run beginTourIfRequested.
vi.mock('../../services/api', () => ({
  setupApi: { bundleInstall: vi.fn().mockResolvedValue({ status: 'already_installed' }) },
  healthApi: {
    authStatus: vi
      .fn()
      .mockResolvedValue({ needs_setup: false, auth_required: false, authenticated: true }),
  },
}));

// useAuth.restore is awaited inside onMounted; stub it.
const restoreMock = vi.fn().mockResolvedValue(undefined);
vi.mock('../useAuth', () => ({
  useAuth: () => ({ restore: restoreMock }),
}));

// Tour-machine prefetch helper is fire-and-forget; stub it to no-op.
const prefetchMock = vi.fn();
vi.mock('../useTourMachine', () => ({
  prefetchTourRoutes: () => prefetchMock(),
}));

import { useAppBoot } from '../useAppBoot';

// ── Helpers ───────────────────────────────────────────────────────────────

function makeTour(active = false) {
  const isActive = ref(active);
  const currentStep = ref('idle');
  return {
    isActive,
    currentStep,
    startTour: vi.fn(() => {
      isActive.value = true;
    }),
    nextStep: vi.fn(),
  };
}

interface MountOpts {
  initialQuery?: { tour?: string };
  tourActive?: boolean;
}

interface Harness {
  tour: ReturnType<typeof makeTour>;
  loadSidebarData: ReturnType<typeof vi.fn>;
  showApiKeyBanner: Ref<boolean>;
  appReady: Ref<boolean>;
}

function mountHost(opts: MountOpts = {}): { wrapper: ReturnType<typeof mount>; harness: Harness } {
  routeQuery.value = opts.initialQuery ?? {};
  routeFullPath.value = '/login';
  const tour = makeTour(opts.tourActive ?? false);
  const loadSidebarData = vi.fn();
  const harness = {
    tour,
    loadSidebarData,
    showApiKeyBanner: ref(false),
    appReady: ref(false),
  } as Harness;

  const Host = defineComponent({
    setup() {
      const result = useAppBoot({
        // Cast: fake tour omits surface useAppBoot doesn't read.
        tour: tour as never,
        loadSidebarData,
        loadPlugins: vi.fn(),
        startPolling: vi.fn(),
        stopPolling: vi.fn(),
        showToast: vi.fn(),
        navigateToTourStep: vi.fn(),
      });
      harness.showApiKeyBanner = result.showApiKeyBanner;
      harness.appReady = result.appReady;
      return () => h('div');
    },
  });

  const wrapper = mount(Host);
  return { wrapper, harness };
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('useAppBoot — ?tour=start watcher', () => {
  beforeEach(() => {
    replaceMock.mockClear();
    pushMock.mockClear();
    prefetchMock.mockClear();
    routeQuery.value = {};
  });

  it('starts the tour when the route mounts with ?tour=start', async () => {
    const { harness } = mountHost({ initialQuery: { tour: 'start' } });
    await flushPromises(); // resolve onMounted's awaits
    expect(harness.tour.startTour).toHaveBeenCalledTimes(1);
    // beginTourIfRequested calls nextStep once (welcome -> workspace).
    expect(harness.tour.nextStep).toHaveBeenCalledTimes(1);
    expect(prefetchMock).toHaveBeenCalledTimes(1);
  });

  it('clears the tour query param via router.replace after starting', async () => {
    mountHost({ initialQuery: { tour: 'start' } });
    await flushPromises();
    expect(replaceMock).toHaveBeenCalledWith({ query: {} });
  });

  it('does NOT start the tour when the query param is absent', async () => {
    const { harness } = mountHost({ initialQuery: {} });
    await flushPromises();
    expect(harness.tour.startTour).not.toHaveBeenCalled();
    expect(harness.tour.nextStep).not.toHaveBeenCalled();
  });

  it('triggers tour start when the watcher fires after mount', async () => {
    const { harness } = mountHost({ initialQuery: {} });
    await flushPromises();
    expect(harness.tour.startTour).not.toHaveBeenCalled();

    // Simulate WelcomePage redirect appending ?tour=start to the route.
    routeQuery.value = { tour: 'start' };
    await flushPromises();

    expect(harness.tour.startTour).toHaveBeenCalledTimes(1);
    expect(replaceMock).toHaveBeenCalledWith({ query: {} });
  });

  it('does not re-start the tour when watcher fires with tour already active', async () => {
    const { harness } = mountHost({ initialQuery: {}, tourActive: true });
    await flushPromises();

    // beginTourIfRequested guards on tour.isActive — set the query but expect
    // no startTour call (already active).
    routeQuery.value = { tour: 'start' };
    await flushPromises();

    expect(harness.tour.startTour).not.toHaveBeenCalled();
  });
});

describe('useAppBoot — stale api-key banner on navigation', () => {
  beforeEach(() => {
    replaceMock.mockClear();
    pushMock.mockClear();
    getApiKeyReturn.value = null;
    routeQuery.value = {};
  });

  // Regression: signing in on /login (the guard's redirect target) never fires
  // the banner's own @authenticated reset, so the pre-auth "API key required"
  // banner used to carry into the app — forcing a SECOND key entry on the main
  // page. Navigating with a key present must hide it and load the sidebar.
  it('hides the stale banner and loads the sidebar when navigating in with a key', async () => {
    getApiKeyReturn.value = 'a-valid-key';
    const { harness } = mountHost();
    await flushPromises();

    // Simulate the stale banner left over from the pre-auth boot.
    harness.showApiKeyBanner.value = true;
    harness.loadSidebarData.mockClear();

    // Navigate /login -> / (what goNext does after api-key sign-in).
    routeFullPath.value = '/';
    await flushPromises();

    expect(harness.showApiKeyBanner.value).toBe(false);
    expect(harness.loadSidebarData).toHaveBeenCalled();
  });

  it('does not re-check auth on navigation when no banner is showing', async () => {
    const { healthApi } = await import('../../services/api');
    const { harness } = mountHost();
    await flushPromises();

    vi.mocked(healthApi.authStatus).mockClear();
    harness.loadSidebarData.mockClear();

    routeFullPath.value = '/projects';
    await flushPromises();

    // Banner was never up, so the watcher must be a no-op (no extra authStatus).
    expect(healthApi.authStatus).not.toHaveBeenCalled();
    expect(harness.loadSidebarData).not.toHaveBeenCalled();
  });
});
