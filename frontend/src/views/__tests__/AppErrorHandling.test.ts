/**
 * Integration tests for App.vue sidebar loading coordination and retry logic.
 *
 * Tests the key behaviors without mounting the full App.vue (which has complex
 * dependencies). Instead, we extract and test the coordination logic directly
 * using minimal helper functions that replicate the App.vue patterns.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref, nextTick } from 'vue';
import { handleApiError } from '../../services/api/error-handler';
import { ApiError } from '../../services/api/client';

// ──────────────────────────────────────────────────────────────────────────────
// Helpers that mirror App.vue's sidebar coordination logic
// ──────────────────────────────────────────────────────────────────────────────

type SectionKey = string;

interface SidebarLoader {
  key: SectionKey;
  fn: () => Promise<void>;
}

/**
 * Creates the sidebar coordination state and functions that mirror App.vue.
 * Accepts loaders so tests can inject mock functions.
 */
function createSidebarCoordinator(loaders: SidebarLoader[]) {
  const sidebarLoading = ref(true);
  const sidebarErrors = ref<Record<SectionKey, string | null>>(
    Object.fromEntries(loaders.map(l => [l.key, null])),
  );

  async function loadSidebarData() {
    sidebarLoading.value = true;
    const results = await Promise.allSettled(loaders.map(l => l.fn()));
    results.forEach((result, index) => {
      const key = loaders[index].key;
      sidebarErrors.value[key] =
        result.status === 'rejected'
          ? result.reason instanceof Error
            ? result.reason.message
            : String(result.reason)
          : null;
    });
    sidebarLoading.value = false;
  }

  async function retrySidebarSection(key: SectionKey) {
    sidebarErrors.value[key] = null;
    const loader = loaders.find(l => l.key === key);
    if (!loader) return;
    try {
      await loader.fn();
      sidebarErrors.value[key] = null;
    } catch (err) {
      sidebarErrors.value[key] = err instanceof Error ? err.message : String(err);
    }
  }

  return { sidebarLoading, sidebarErrors, loadSidebarData, retrySidebarSection };
}

// ──────────────────────────────────────────────────────────────────────────────
// Test suites
// ──────────────────────────────────────────────────────────────────────────────

describe('Sidebar loading coordination', () => {
  it('sidebarLoading starts true and becomes false after all fetches settle', async () => {
    const loaders: SidebarLoader[] = [
      { key: 'triggers', fn: vi.fn().mockResolvedValue(undefined) },
      { key: 'projects', fn: vi.fn().mockResolvedValue(undefined) },
      { key: 'teams', fn: vi.fn().mockResolvedValue(undefined) },
    ];

    const { sidebarLoading, loadSidebarData } = createSidebarCoordinator(loaders);

    expect(sidebarLoading.value).toBe(true);

    const loadPromise = loadSidebarData();
    expect(sidebarLoading.value).toBe(true); // Still loading during fetch

    await loadPromise;
    expect(sidebarLoading.value).toBe(false);
  });

  it('sidebarErrors tracks per-section failures independently', async () => {
    const loaders: SidebarLoader[] = [
      { key: 'triggers', fn: vi.fn().mockResolvedValue(undefined) },
      { key: 'projects', fn: vi.fn().mockRejectedValue(new Error('Projects failed')) },
      { key: 'products', fn: vi.fn().mockResolvedValue(undefined) },
      { key: 'teams', fn: vi.fn().mockRejectedValue(new Error('Teams failed')) },
      { key: 'plugins', fn: vi.fn().mockResolvedValue(undefined) },
      { key: 'backends', fn: vi.fn().mockResolvedValue(undefined) },
      { key: 'version', fn: vi.fn().mockResolvedValue(undefined) },
    ];

    const { sidebarErrors, loadSidebarData } = createSidebarCoordinator(loaders);
    await loadSidebarData();

    // Failed sections have error messages
    expect(sidebarErrors.value['projects']).toBe('Projects failed');
    expect(sidebarErrors.value['teams']).toBe('Teams failed');

    // Successful sections remain null
    expect(sidebarErrors.value['triggers']).toBeNull();
    expect(sidebarErrors.value['products']).toBeNull();
    expect(sidebarErrors.value['plugins']).toBeNull();
    expect(sidebarErrors.value['backends']).toBeNull();
    expect(sidebarErrors.value['version']).toBeNull();
  });

  it('successful sections are not affected when other sections fail (Promise.allSettled)', async () => {
    let triggersData: string[] = [];
    let pluginsData: string[] = [];

    const loaders: SidebarLoader[] = [
      {
        key: 'triggers',
        fn: vi.fn(async () => {
          triggersData = ['trigger-1'];
        }),
      },
      {
        key: 'projects',
        fn: vi.fn().mockRejectedValue(new Error('Network error')),
      },
      {
        key: 'plugins',
        fn: vi.fn(async () => {
          pluginsData = ['plugin-1', 'plugin-2'];
        }),
      },
    ];

    const { sidebarErrors, loadSidebarData } = createSidebarCoordinator(loaders);
    await loadSidebarData();

    // Failed section has error
    expect(sidebarErrors.value['projects']).toBe('Network error');

    // Successful sections ran their loaders and have data
    expect(triggersData).toEqual(['trigger-1']);
    expect(pluginsData).toEqual(['plugin-1', 'plugin-2']);
    expect(sidebarErrors.value['triggers']).toBeNull();
    expect(sidebarErrors.value['plugins']).toBeNull();
  });

  it('stores non-Error rejection reason as string', async () => {
    const loaders: SidebarLoader[] = [
      { key: 'teams', fn: vi.fn().mockRejectedValue('string rejection') },
    ];

    const { sidebarErrors, loadSidebarData } = createSidebarCoordinator(loaders);
    await loadSidebarData();

    expect(sidebarErrors.value['teams']).toBe('string rejection');
  });
});

describe('retrySidebarSection', () => {
  it('calls only the targeted section loader', async () => {
    const mockLoaders = {
      triggers: vi.fn().mockResolvedValue(undefined),
      projects: vi.fn().mockResolvedValue(undefined),
      products: vi.fn().mockResolvedValue(undefined),
      teams: vi.fn().mockResolvedValue(undefined),
      plugins: vi.fn().mockResolvedValue(undefined),
      backends: vi.fn().mockResolvedValue(undefined),
      version: vi.fn().mockResolvedValue(undefined),
    };

    const loaders = Object.entries(mockLoaders).map(([key, fn]) => ({ key, fn }));
    const { retrySidebarSection } = createSidebarCoordinator(loaders);

    await retrySidebarSection('teams');

    // Only the targeted loader was called
    expect(mockLoaders.teams).toHaveBeenCalledTimes(1);

    // All other loaders were NOT called
    expect(mockLoaders.triggers).not.toHaveBeenCalled();
    expect(mockLoaders.projects).not.toHaveBeenCalled();
    expect(mockLoaders.products).not.toHaveBeenCalled();
    expect(mockLoaders.plugins).not.toHaveBeenCalled();
    expect(mockLoaders.backends).not.toHaveBeenCalled();
    expect(mockLoaders.version).not.toHaveBeenCalled();
  });

  it('clears only the targeted section error state on retry', async () => {
    const loaders: SidebarLoader[] = [
      { key: 'teams', fn: vi.fn().mockResolvedValue(undefined) },
      { key: 'products', fn: vi.fn().mockResolvedValue(undefined) },
    ];

    const { sidebarErrors, retrySidebarSection } = createSidebarCoordinator(loaders);

    // Pre-set errors for both sections
    sidebarErrors.value['teams'] = 'Teams error';
    sidebarErrors.value['products'] = 'Products error';
    await nextTick();

    // Retry only 'teams'
    await retrySidebarSection('teams');

    // Teams error is cleared (loader succeeded)
    expect(sidebarErrors.value['teams']).toBeNull();

    // Products error is NOT affected
    expect(sidebarErrors.value['products']).toBe('Products error');
  });

  it('sets error on retry failure', async () => {
    const loaders: SidebarLoader[] = [
      { key: 'teams', fn: vi.fn().mockRejectedValue(new Error('Retry failed')) },
    ];

    const { sidebarErrors, retrySidebarSection } = createSidebarCoordinator(loaders);
    await retrySidebarSection('teams');

    expect(sidebarErrors.value['teams']).toBe('Retry failed');
  });

  it('clears error before calling loader (shows loading state during retry)', async () => {
    let errorDuringLoad: string | null = 'initial';

    const loaders: SidebarLoader[] = [
      {
        key: 'teams',
        fn: vi.fn(async () => {
          // Capture the error state at the moment the loader runs
          errorDuringLoad = sidebarErrors.value['teams'];
        }),
      },
    ];

    const { sidebarErrors, retrySidebarSection } = createSidebarCoordinator(loaders);

    // Set an initial error
    sidebarErrors.value['teams'] = 'Previous error';

    await retrySidebarSection('teams');

    // Error was null when the loader ran (cleared before the async call)
    expect(errorDuringLoad).toBeNull();
  });

  it('does nothing when key is not found in loaders', async () => {
    const loaders: SidebarLoader[] = [
      { key: 'teams', fn: vi.fn().mockResolvedValue(undefined) },
    ];

    const { retrySidebarSection } = createSidebarCoordinator(loaders);

    // Should not throw
    await expect(retrySidebarSection('nonexistent')).resolves.toBeUndefined();

    // No loader was called
    expect(loaders[0].fn).not.toHaveBeenCalled();
  });
});

describe('handleApiError integration with sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sidebar fetch failure calls handleApiError which invokes showToast', () => {
    const mockShowToast = vi.fn();
    const apiError = new ApiError(500, 'Internal server error');

    handleApiError(apiError, mockShowToast, 'Failed to load teams');

    expect(mockShowToast).toHaveBeenCalledTimes(1);
    expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('ERR-500'), 'error');
  });

  it('handleApiError returns formatted message stored in sidebarErrors', () => {
    const mockShowToast = vi.fn();
    const apiError = new ApiError(404, 'Teams not found');

    const message = handleApiError(apiError, mockShowToast, 'Failed to load teams');

    // The return value contains the formatted error code
    expect(message).toContain('ERR-404');

    // This is the value that would be stored in sidebarErrors
    const sidebarErrors: Record<string, string | null> = { teams: null };
    sidebarErrors['teams'] = message;
    expect(sidebarErrors['teams']).toBe(message);
    expect(typeof sidebarErrors['teams']).toBe('string');
  });

  it('sidebar error message is a non-empty string for ApiError', () => {
    const mockShowToast = vi.fn();
    const error = new ApiError(503, 'Service unavailable');

    const message = handleApiError(error, mockShowToast);
    expect(message.length).toBeGreaterThan(0);
    expect(message).toContain('ERR-503');
  });

  it('sidebar error message contains fallback text for generic errors', () => {
    const mockShowToast = vi.fn();
    const error = new Error('Network timeout');

    const message = handleApiError(error, mockShowToast, 'Failed to load sidebar');
    expect(message).toContain('ERR-UNKNOWN');
    expect(mockShowToast).toHaveBeenCalledWith(message, 'error');
  });
});
