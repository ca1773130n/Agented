/**
 * PR-G — AnomalyDetectionCard 501 banner regression guard.
 *
 * The backend handlers (`GET /admin/executions/anomalies` and
 * `POST /admin/executions/anomalies/{id}/acknowledge`) now return 501
 * ("Feature not yet enabled"). The card must:
 *   1. Render a static "not yet enabled" banner.
 *   2. NOT fall through to the legacy demo-on-failure fallback that
 *      previously masked the missing feature with synthetic anomalies.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('../../../../composables/useToast', () => ({
  useToast: () => () => undefined,
}));

import AnomalyDetectionCard from '../AnomalyDetectionCard.vue';

function build501Response(): Response {
  return new Response(
    JSON.stringify({ error: { code: 'HTTP_ERROR', message: 'Feature not yet enabled' } }),
    { status: 501, headers: { 'Content-Type': 'application/json' } },
  ) as unknown as Response;
}

describe('AnomalyDetectionCard — PR-G 501 banner', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the "not yet enabled" banner when GET anomalies returns 501', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(build501Response());

    const w = mount(AnomalyDetectionCard);
    await flushPromises();

    expect(fetchSpy).toHaveBeenCalledWith('/admin/executions/anomalies');
    const banner = w.find('[data-testid="anomaly-not-enabled"]');
    expect(banner.exists()).toBe(true);
    expect(banner.text()).toContain('Anomaly detection is not yet enabled');

    // Demo-on-failure fallback must NOT fire — no anomaly cards, no
    // baseline rows, no stats grid (the "v-else" tree is not rendered).
    expect(w.find('.anomaly-list').exists()).toBe(false);
    expect(w.find('.baseline-section').exists()).toBe(false);
    expect(w.text()).not.toContain('No active anomalies');
  });

  it('falls through to demo data on network error (not 501)', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network down'));

    const w = mount(AnomalyDetectionCard);
    await flushPromises();

    // No 501 banner; the legacy demo fallback is active.
    expect(w.find('[data-testid="anomaly-not-enabled"]').exists()).toBe(false);
    expect(w.find('.anomaly-list').exists()).toBe(true);
  });
});
