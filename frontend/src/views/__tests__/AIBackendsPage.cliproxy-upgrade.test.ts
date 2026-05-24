/**
 * PR-M — Upgrade CLIProxy button on AIBackendsPage triggers
 * backendManagementApi.upgradeCliproxy() and surfaces the result via toast.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { defineComponent, h } from 'vue';
import AIBackendsPage from '../AIBackendsPage.vue';

const upgradeCliproxy = vi.fn();
const installCli = vi.fn();
const check = vi.fn();
const proxyLogin = vi.fn();
const listGroupedBackends = vi.fn();
const discoverConfigs = vi.fn();
const importDiscovered = vi.fn();
const toastSpy = vi.fn();

vi.mock('../../services/api', () => ({
  backendManagementApi: {
    installCli: (...a: unknown[]) => installCli(...a),
    check: (...a: unknown[]) => check(...a),
    proxyLogin: (...a: unknown[]) => proxyLogin(...a),
    upgradeCliproxy: (...a: unknown[]) => upgradeCliproxy(...a),
  },
  listGroupedBackends: (...a: unknown[]) => listGroupedBackends(...a),
}));

vi.mock('../../composables/useToast', () => ({
  useToast: () => toastSpy,
}));

vi.mock('@ai-accounts/vue-headless', () => ({
  useAiAccounts: () => ({
    client: {
      discoverConfigs: (...a: unknown[]) => discoverConfigs(...a),
      importDiscovered: (...a: unknown[]) => importDiscovered(...a),
    },
  }),
}));

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'ai-backends', component: AIBackendsPage },
      { path: '/backends/:backendId', name: 'backend-detail', component: defineComponent({ render: () => h('div', 'detail') }) },
    ],
  });
}

async function mountPage(): Promise<VueWrapper> {
  const router = buildRouter();
  router.push('/');
  await router.isReady();
  const wrapper = mount(AIBackendsPage, { global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}

describe('AIBackendsPage — Upgrade CLIProxy', () => {
  beforeEach(() => {
    upgradeCliproxy.mockReset();
    toastSpy.mockReset();
    listGroupedBackends.mockResolvedValue({ backends: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders the upgrade button', async () => {
    const w = await mountPage();
    expect(w.find('[data-testid="upgrade-cliproxy-btn"]').exists()).toBe(true);
  });

  it('calls upgradeCliproxy on click and surfaces success toast with version', async () => {
    upgradeCliproxy.mockResolvedValue({ success: true, message: 'ok', version: '1.2.3' });
    listGroupedBackends.mockClear();

    const w = await mountPage();
    await w.get('[data-testid="upgrade-cliproxy-btn"]').trigger('click');
    await flushPromises();

    expect(upgradeCliproxy).toHaveBeenCalledTimes(1);
    expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining('v1.2.3'), 'success');
    // Backends refreshed after upgrade
    expect(listGroupedBackends).toHaveBeenCalled();
  });

  it('shows an error toast when the backend reports success=false', async () => {
    upgradeCliproxy.mockResolvedValue({ success: false, message: 'binary not found', version: null });

    const w = await mountPage();
    await w.get('[data-testid="upgrade-cliproxy-btn"]').trigger('click');
    await flushPromises();

    expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining('binary not found'), 'error');
  });

  it('surfaces a toast error when the request rejects (e.g. 403 non-admin)', async () => {
    upgradeCliproxy.mockRejectedValue(new Error('Forbidden'));

    const w = await mountPage();
    await w.get('[data-testid="upgrade-cliproxy-btn"]').trigger('click');
    await flushPromises();

    expect(toastSpy).toHaveBeenCalledWith('Forbidden', 'error');
  });
});
