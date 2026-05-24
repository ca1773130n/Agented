/**
 * PR-G — ExecutionQuotaControls 501 banner regression guard.
 *
 * The mutating backend handlers (POST/PUT/DELETE /executions/quotas) now
 * return 501 ("Feature not yet enabled"). The page must render a static
 * banner at the top and disable the create form submit button so
 * operators don't believe their changes persisted.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('../../composables/useToast', () => ({
  useToast: () => () => undefined,
}));

import ExecutionQuotaControls from '../ExecutionQuotaControls.vue';

function buildEmptyQuotasResponse(): Response {
  return new Response(JSON.stringify({ rules: [] }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }) as unknown as Response;
}

describe('ExecutionQuotaControls — PR-G 501 banner', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the "not yet enabled" banner and disables the create submit button', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(buildEmptyQuotasResponse());

    const w = mount(ExecutionQuotaControls);
    await flushPromises();

    const banner = w.find('[data-testid="quotas-not-enabled"]');
    expect(banner.exists()).toBe(true);
    expect(banner.text()).toContain('Quota enforcement is not yet enabled');

    // Open the create form, then confirm the submit button is disabled.
    const newRuleBtn = w.findAll('button').find((b) => b.text().includes('New Rule'));
    expect(newRuleBtn?.exists()).toBe(true);
    expect(newRuleBtn?.attributes('disabled')).toBeDefined();
  });
});
