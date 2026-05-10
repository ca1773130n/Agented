import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('../../../services/api/model-cache', () => ({
  modelCacheApi: {
    list: vi.fn(),
    refresh: vi.fn(),
    cacheOverview: vi.fn(),
  },
}));

import BackendInfoSection from '../BackendInfoSection.vue';
import { modelCacheApi } from '../../../services/api/model-cache';

function mountSection(overrides: Record<string, unknown> = {}) {
  return mount(BackendInfoSection, {
    props: {
      models: ['gpt-5'],
      capabilityList: [],
      cliPath: null,
      ...overrides,
    },
  });
}

describe('BackendInfoSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders provided models', () => {
    const wrapper = mountSection({ models: ['gpt-5', 'gpt-4o'] });
    const tags = wrapper.findAll('.model-tag').map((t) => t.text());
    expect(tags).toEqual(['gpt-5', 'gpt-4o']);
  });

  it('does NOT render the refresh button when backendKind is missing', () => {
    const wrapper = mountSection();
    expect(wrapper.find('[data-testid="refresh-models-btn"]').exists()).toBe(false);
  });

  it('renders the refresh button when backendKind is provided', () => {
    const wrapper = mountSection({ backendKind: 'codex' });
    expect(wrapper.find('[data-testid="refresh-models-btn"]').exists()).toBe(true);
  });

  it('refresh button click calls modelCacheApi.refresh and updates models', async () => {
    (modelCacheApi.refresh as ReturnType<typeof vi.fn>).mockResolvedValue({
      models: ['gpt-5', 'gpt-5.1'],
      backend_kind: 'codex',
      auth_method: 'api_key',
      discovery_method: 'mixed',
      discovered_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 7 * 86400_000).toISOString(),
      error_message: null,
      fresh: true,
    });
    const wrapper = mountSection({
      models: ['gpt-5'],
      backendKind: 'codex',
      authMethod: 'api_key',
    });
    await wrapper.find('[data-testid="refresh-models-btn"]').trigger('click');
    await flushPromises();
    expect(modelCacheApi.refresh).toHaveBeenCalledWith('codex', 'api_key');
    // v0.7.8 follow-up: refresh now returns models, so list() is no longer called.
    expect(modelCacheApi.list).not.toHaveBeenCalled();
    const tags = wrapper.findAll('.model-tag').map((t) => t.text());
    expect(tags).toEqual(['gpt-5', 'gpt-5.1']);
    expect(wrapper.find('[data-testid="discovered-at"]').exists()).toBe(true);
  });

  it('defaults authMethod to "unknown" when not provided', async () => {
    (modelCacheApi.refresh as ReturnType<typeof vi.fn>).mockResolvedValue({
      models: ['gpt-5'],
      backend_kind: 'codex',
      auth_method: 'unknown',
      discovery_method: 'mixed',
      discovered_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 7 * 86400_000).toISOString(),
      error_message: null,
      fresh: true,
    });
    const wrapper = mountSection({ models: [], backendKind: 'codex' });
    await wrapper.find('[data-testid="refresh-models-btn"]').trigger('click');
    await flushPromises();
    expect(modelCacheApi.refresh).toHaveBeenCalledWith('codex', 'unknown');
  });

  it('shows the spinner while refreshing', async () => {
    let resolveRefresh!: (v: unknown) => void;
    (modelCacheApi.refresh as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise((res) => {
        resolveRefresh = res;
      }),
    );
    const wrapper = mountSection({ backendKind: 'codex' });
    await wrapper.find('[data-testid="refresh-models-btn"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="refresh-spinner"]').exists()).toBe(true);
    resolveRefresh({
      models: [],
      backend_kind: 'codex',
      auth_method: 'unknown',
      discovery_method: 'mixed',
      discovered_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 7 * 86400_000).toISOString(),
      error_message: null,
      fresh: true,
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="refresh-spinner"]').exists()).toBe(false);
  });

  it('surfaces API errors inline', async () => {
    (modelCacheApi.refresh as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('subprocess died'),
    );
    const wrapper = mountSection({ backendKind: 'codex' });
    await wrapper.find('[data-testid="refresh-models-btn"]').trigger('click');
    await flushPromises();
    const err = wrapper.find('[data-testid="refresh-error"]');
    expect(err.exists()).toBe(true);
    expect(err.text()).toContain('subprocess died');
  });

  it('discovered-at label ticks forward as time advances', async () => {
    vi.useFakeTimers();
    const fixedAt = new Date('2026-05-10T00:00:00.000Z');
    vi.setSystemTime(fixedAt);
    (modelCacheApi.refresh as ReturnType<typeof vi.fn>).mockResolvedValue({
      models: ['gpt-5'],
      backend_kind: 'codex',
      auth_method: 'unknown',
      discovery_method: 'mixed',
      discovered_at: fixedAt.toISOString(),
      expires_at: '2026-05-17T00:00:00.000Z',
      error_message: null,
      fresh: true,
    });
    const wrapper = mountSection({ backendKind: 'codex' });
    await wrapper.find('[data-testid="refresh-models-btn"]').trigger('click');
    await flushPromises();
    // Advance just enough to render a small "seconds ago" value.
    vi.setSystemTime(new Date(fixedAt.getTime() + 5_000));
    await wrapper.vm.$nextTick();
    const initial = wrapper.find('[data-testid="discovered-at"]').text();
    expect(initial).toBeTruthy();
    // Advance past the 30s tick boundary; expect label to re-render.
    vi.setSystemTime(new Date(fixedAt.getTime() + 2 * 60_000));
    vi.advanceTimersByTime(60_000);
    await wrapper.vm.$nextTick();
    const later = wrapper.find('[data-testid="discovered-at"]').text();
    expect(later).toBeTruthy();
    expect(later).not.toBe(initial);
    vi.useRealTimers();
  });

  it('clears the tick interval on unmount', () => {
    const clearSpy = vi.spyOn(globalThis, 'clearInterval');
    const wrapper = mountSection({ backendKind: 'codex' });
    wrapper.unmount();
    expect(clearSpy).toHaveBeenCalled();
    clearSpy.mockRestore();
  });

  // v0.7.9: discovery_method surfaces in the UI so operators can tell whether
  // the models came from the authoritative sidecar path or a local fallback.
  it('renders the "via sidecar" label when discovery_method is "sidecar"', async () => {
    (modelCacheApi.refresh as ReturnType<typeof vi.fn>).mockResolvedValue({
      models: ['claude-opus-4-7'],
      backend_kind: 'claude',
      auth_method: 'cli_browser',
      discovery_method: 'sidecar',
      discovered_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 7 * 86400_000).toISOString(),
      error_message: null,
      fresh: true,
    });
    const wrapper = mountSection({ backendKind: 'claude', authMethod: 'cli_browser' });
    await wrapper.find('[data-testid="refresh-models-btn"]').trigger('click');
    await flushPromises();
    const label = wrapper.find('[data-testid="discovery-method"]');
    expect(label.exists()).toBe(true);
    expect(label.text().toLowerCase()).toContain('sidecar');
    // Sidecar is authoritative — should NOT carry the warning class.
    expect(label.classes()).not.toContain('discovery-method-warn');
  });

  it('renders the "via local" label and warning when discovery_method is "local"', async () => {
    (modelCacheApi.refresh as ReturnType<typeof vi.fn>).mockResolvedValue({
      models: ['claude-opus-4-6'],
      backend_kind: 'claude',
      auth_method: 'cli_browser',
      discovery_method: 'local',
      discovered_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 7 * 86400_000).toISOString(),
      error_message: null,
      fresh: true,
    });
    const wrapper = mountSection({ backendKind: 'claude', authMethod: 'cli_browser' });
    await wrapper.find('[data-testid="refresh-models-btn"]').trigger('click');
    await flushPromises();
    const label = wrapper.find('[data-testid="discovery-method"]');
    expect(label.exists()).toBe(true);
    expect(label.text().toLowerCase()).toContain('local');
    // Non-sidecar sources carry the warning class so operators notice.
    expect(label.classes()).toContain('discovery-method-warn');
  });

  it('emits models-refreshed with the new list', async () => {
    const fixedAt = '2026-05-10T00:00:00.000Z';
    (modelCacheApi.refresh as ReturnType<typeof vi.fn>).mockResolvedValue({
      models: ['gpt-5'],
      backend_kind: 'codex',
      auth_method: 'unknown',
      discovery_method: 'mixed',
      discovered_at: fixedAt,
      expires_at: '2026-05-17T00:00:00.000Z',
      error_message: null,
      fresh: true,
    });
    const wrapper = mountSection({ backendKind: 'codex' });
    await wrapper.find('[data-testid="refresh-models-btn"]').trigger('click');
    await flushPromises();
    const evts = wrapper.emitted('models-refreshed');
    expect(evts).toBeTruthy();
    expect(evts?.[0][0]).toEqual({
      models: ['gpt-5'],
      discoveredAt: fixedAt,
    });
  });
});
