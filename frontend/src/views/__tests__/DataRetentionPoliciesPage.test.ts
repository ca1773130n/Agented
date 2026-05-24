/**
 * PR-R (wave 83) — DataRetentionPoliciesPage smoke test.
 *
 * Verifies the "Not yet enabled" banner is gone now that the feature is
 * real, and that the action buttons are no longer disabled.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('../../composables/useToast', () => ({
  useToast: () => () => undefined,
}));

vi.mock('../../services/api/retention', () => ({
  retentionApi: {
    list: vi.fn().mockResolvedValue({ policies: [] }),
    create: vi.fn(),
    toggle: vi.fn(),
    delete: vi.fn(),
    runCleanup: vi.fn().mockResolvedValue({ message: 'Cleanup queued' }),
  },
}));

import DataRetentionPoliciesPage from '../DataRetentionPoliciesPage.vue';

describe('DataRetentionPoliciesPage — PR-R real feature', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not render the NotEnabledBanner', async () => {
    const w = mount(DataRetentionPoliciesPage);
    await flushPromises();

    const banner = w.find('[data-testid="data-retention-not-enabled"]');
    expect(banner.exists()).toBe(false);
  });

  it('renders Add Policy and Run Cleanup buttons as enabled', async () => {
    const w = mount(DataRetentionPoliciesPage);
    await flushPromises();

    const addBtn = w.findAll('button').find((b) => b.text().includes('Add Policy'));
    expect(addBtn?.exists()).toBe(true);
    expect(addBtn?.attributes('disabled')).toBeUndefined();

    const cleanupBtn = w
      .findAll('button')
      .find((b) => b.text().includes('Run Cleanup Now'));
    expect(cleanupBtn?.exists()).toBe(true);
    expect(cleanupBtn?.attributes('disabled')).toBeUndefined();
  });
});
