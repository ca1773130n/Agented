/**
 * PR-G — ReportDigestsPage 501 banner regression guard.
 *
 * The mutating backend handlers (POST/PUT /reports/digests) now return
 * 501 ("Feature not yet enabled"). The page must render a static banner
 * at the top and disable the create + edit submit buttons.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('../../composables/useToast', () => ({
  useToast: () => () => undefined,
}));

import ReportDigestsPage from '../ReportDigestsPage.vue';

function buildEmptyDigestsResponse(): Response {
  return new Response(JSON.stringify({ digests: [] }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }) as unknown as Response;
}

describe('ReportDigestsPage — PR-G 501 banner', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the "not yet enabled" banner and disables the Add Digest button', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(buildEmptyDigestsResponse());

    const w = mount(ReportDigestsPage);
    await flushPromises();

    const banner = w.find('[data-testid="digests-not-enabled"]');
    expect(banner.exists()).toBe(true);
    expect(banner.text()).toContain('Digest delivery is not yet enabled');

    // The header "+ Add Digest" button must be disabled.
    const addBtn = w.findAll('button').find((b) => b.text().includes('+ Add Digest'));
    expect(addBtn?.exists()).toBe(true);
    expect(addBtn?.attributes('disabled')).toBeDefined();
  });
});
