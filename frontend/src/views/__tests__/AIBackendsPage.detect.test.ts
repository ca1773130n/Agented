import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import {
  createRouter,
  createMemoryHistory,
  type Router,
} from 'vue-router';
import { defineComponent, h } from 'vue';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Stub the Agented API surface — AIBackendsPage calls listGroupedBackends()
// on mount via loadBackends().  We resolve to an empty list so the empty
// state (which now hosts the Detect CTA) renders.
vi.mock('../../services/api', () => ({
  backendManagementApi: {
    installCli: vi.fn(),
    proxyLogin: vi.fn(),
    check: vi.fn().mockResolvedValue({ capabilities: null }),
  },
  listGroupedBackends: vi.fn().mockResolvedValue({ backends: [] }),
}));

// Stub the credentials banner — it self-fetches on mount and we don't care
// about its surface in these tests.
vi.mock('../../components/credentials/CredentialStatusBanner.vue', () => ({
  default: defineComponent({
    name: 'CredentialStatusBanner',
    render: () => h('div', { class: 'stub-credential-banner' }),
  }),
}));

// Toast — capture for assertions.
const toastSpy = vi.fn();
vi.mock('../../composables/useToast', () => ({
  useToast: () => toastSpy,
}));

// Mock the ai-accounts client returned by useAiAccounts().
const discoverConfigs = vi.fn();
const importDiscovered = vi.fn();
vi.mock('@ai-accounts/vue-headless', () => ({
  useAiAccounts: () => ({
    client: {
      discoverConfigs,
      importDiscovered,
    },
  }),
}));

// vue-styled exports AiChatPanel — stub it (the global stub registered in
// src/test/setup.ts already covers the component-tag form, but the SFC
// imports it directly so we also intercept the module import).
vi.mock('@ai-accounts/vue-styled', () => ({
  AiChatPanel: defineComponent({
    name: 'AiChatPanel',
    render: () => h('div', { class: 'stub-ai-chat-panel' }),
  }),
}));

import AIBackendsPage from '../AIBackendsPage.vue';
import { listGroupedBackends } from '../../services/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const StubView = defineComponent({
  name: 'StubView',
  render: () => h('div'),
});

function buildRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'ai-backends', component: AIBackendsPage },
      {
        path: '/backends/:backendId',
        name: 'backend-detail',
        component: StubView,
      },
    ],
  });
}

async function mountPage(): Promise<VueWrapper> {
  const router = buildRouter();
  router.push('/');
  await router.isReady();
  const wrapper = mount(AIBackendsPage, {
    global: {
      plugins: [router],
    },
  });
  await flushPromises();
  return wrapper;
}

const sampleItems = [
  {
    kind: 'claude',
    path: '/Users/test/.claude',
    suggested_name: 'Personal Claude',
    is_logged_in: true,
    error: null,
    backend_id: null,
  },
  {
    kind: 'codex',
    path: '/Users/test/.codex',
    suggested_name: 'Work Codex',
    is_logged_in: true,
    error: null,
    backend_id: 'bk-existing',
  },
  {
    kind: 'gemini',
    path: '/Users/test/.gemini',
    suggested_name: 'Stale Gemini',
    is_logged_in: false,
    error: 'gemini -p exited 1',
    backend_id: null,
  },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AIBackendsPage — auto-discovery', () => {
  beforeEach(() => {
    discoverConfigs.mockReset();
    importDiscovered.mockReset();
    toastSpy.mockReset();
    vi.mocked(listGroupedBackends).mockResolvedValue({ backends: [] });
  });

  it('does NOT call discoverConfigs on mount (probe is expensive)', async () => {
    discoverConfigs.mockResolvedValue({ items: [] });
    await mountPage();
    expect(discoverConfigs).not.toHaveBeenCalled();
  });

  it('opens the modal and runs discovery on Detect Existing click', async () => {
    discoverConfigs.mockResolvedValue({ items: sampleItems });

    const wrapper = await mountPage();
    expect(wrapper.find('[data-testid="detect-modal"]').exists()).toBe(false);

    await wrapper.get('[data-testid="detect-existing-btn"]').trigger('click');
    await flushPromises();

    expect(discoverConfigs).toHaveBeenCalledTimes(1);
    expect(document.body.querySelector('[data-testid="detect-modal"]')).toBeTruthy();
    expect(document.body.querySelector('[data-testid="detect-list"]')).toBeTruthy();

    const modalText = document.body.querySelector('[data-testid="detect-modal"]')?.textContent ?? '';
    expect(modalText).toContain('Personal Claude');
    expect(modalText).toContain('Work Codex');
    expect(modalText).toContain('Stale Gemini');
    // Already-imported badge for the codex row
    expect(document.body.querySelector('[data-testid="already-imported"]')).toBeTruthy();
    // Import button only for the logged-in, not-yet-imported claude row
    expect(document.body.querySelector('[data-testid="detect-import-claude"]')).toBeTruthy();
    expect(document.body.querySelector('[data-testid="detect-import-codex"]')).toBeFalsy();
    // Not-logged-in row shows hint, no import button
    expect(document.body.querySelector('[data-testid="detect-import-gemini"]')).toBeFalsy();
  });

  it('shows empty-state copy when discovery returns no items', async () => {
    discoverConfigs.mockResolvedValue({ items: [] });

    const wrapper = await mountPage();
    await wrapper.get('[data-testid="detect-existing-btn"]').trigger('click');
    await flushPromises();

    expect(document.body.querySelector('[data-testid="detect-empty"]')).toBeTruthy();
    expect(toastSpy).toHaveBeenCalledWith(
      expect.stringContaining('No existing CLI logins'),
      'info',
    );
  });

  it('imports a candidate and reloads the backend list', async () => {
    discoverConfigs.mockResolvedValue({ items: [sampleItems[0]] });
    importDiscovered.mockResolvedValue({ id: 'bk-new' });

    const wrapper = await mountPage();
    await wrapper.get('[data-testid="detect-existing-btn"]').trigger('click');
    await flushPromises();

    vi.mocked(listGroupedBackends).mockClear();

    const importBtn = document.body.querySelector('[data-testid="detect-import-claude"]') as HTMLButtonElement;
    expect(importBtn).toBeTruthy();
    importBtn.click();
    await flushPromises();

    expect(importDiscovered).toHaveBeenCalledWith({
      kind: 'claude',
      path: '/Users/test/.claude',
      display_name: 'Personal Claude',
    });
    expect(toastSpy).toHaveBeenCalledWith(
      expect.stringContaining('Imported Personal Claude'),
      'success',
    );
    expect(listGroupedBackends).toHaveBeenCalledTimes(1);
    // Row flips to "Already imported" locally without a rescan.
    expect(document.body.querySelector('[data-testid="already-imported"]')).toBeTruthy();
    expect(discoverConfigs).toHaveBeenCalledTimes(1); // no rescan
  });

  it('surfaces a toast error when discovery throws', async () => {
    discoverConfigs.mockRejectedValue(new Error('sidecar offline'));

    const wrapper = await mountPage();
    await wrapper.get('[data-testid="detect-existing-btn"]').trigger('click');
    await flushPromises();

    expect(toastSpy).toHaveBeenCalledWith('sidecar offline', 'error');
  });

  it('exposes a Detect CTA from the empty state when no backends are configured', async () => {
    discoverConfigs.mockResolvedValue({ items: [] });
    const wrapper = await mountPage();
    const emptyBtn = wrapper.find('[data-testid="detect-existing-empty-btn"]');
    expect(emptyBtn.exists()).toBe(true);
    await emptyBtn.trigger('click');
    await flushPromises();
    expect(discoverConfigs).toHaveBeenCalledTimes(1);
  });
});
