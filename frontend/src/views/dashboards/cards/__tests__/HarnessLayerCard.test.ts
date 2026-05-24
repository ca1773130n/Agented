/**
 * HarnessLayerCard — colour-coded Life-Harness summary on the Activity lane.
 *
 * Verifies the card calls the summary API on mount, renders one badge per
 * layer with the right counts, and lists recent failures with the matching
 * primary-layer pill.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, h } from 'vue';

// vi.mock is hoisted to the top of the file, so the spy has to be created
// inside vi.hoisted() to be available when the factory runs.
const { getSummary, getForExecution } = vi.hoisted(() => ({
  getSummary: vi.fn(),
  getForExecution: vi.fn(),
}));

vi.mock('../../../../services/api/harness-annotations', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/api/harness-annotations')
  >('../../../../services/api/harness-annotations');
  return {
    ...actual,
    harnessAnnotationsApi: { getSummary, getForExecution },
  };
});

// Stub the LoadingState / ErrorState shells so we render predictable markup.
vi.mock('../../../../components/base/LoadingState.vue', () => ({
  default: defineComponent({ render: () => h('div', { class: 'loading-stub' }) }),
}));
vi.mock('../../../../components/base/ErrorState.vue', () => ({
  default: defineComponent({ render: () => h('div', { class: 'error-stub' }) }),
}));

import HarnessLayerCard from '../HarnessLayerCard.vue';

beforeEach(() => {
  getSummary.mockReset();
});

describe('HarnessLayerCard', () => {
  it('renders one badge per layer with the API counts', async () => {
    getSummary.mockResolvedValue({
      since: null,
      by_layer: { h2: 5, h3: 2, h4: 7, general: 1, none: 11, total: 26 },
      recent_failures: [],
    });
    const w = mount(HarnessLayerCard);
    await flushPromises();

    expect(getSummary).toHaveBeenCalledWith({ limit: 5 });
    const badges = w.findAll('[data-testid^="harness-layer-badge-"]');
    expect(badges).toHaveLength(4);

    const counts = Object.fromEntries(
      badges.map((b) => [
        b.attributes('data-testid')!.replace('harness-layer-badge-', ''),
        b.find('.badge__count').text(),
      ]),
    );
    expect(counts).toEqual({ h2: '5', h3: '2', h4: '7', general: '1' });
    expect(w.text()).toContain('26 executions annotated');
    expect(w.text()).toContain('11 clean');
  });

  it('shows the empty state when nothing is annotated yet', async () => {
    getSummary.mockResolvedValue({
      since: null,
      by_layer: { h2: 0, h3: 0, h4: 0, general: 0, none: 0, total: 0 },
      recent_failures: [],
    });
    const w = mount(HarnessLayerCard);
    await flushPromises();

    expect(w.find('[data-testid="harness-layer-empty"]').exists()).toBe(true);
    expect(w.findAll('[data-testid^="harness-layer-badge-"]')).toHaveLength(0);
  });

  it('lists recent failures with the primary-layer pill', async () => {
    getSummary.mockResolvedValue({
      since: null,
      by_layer: { h2: 1, h3: 0, h4: 0, general: 0, none: 0, total: 1 },
      recent_failures: [
        {
          session_kind: 'trigger_execution',
          session_id: 'exec-zzz',
          project_id: null,
          primary_layer: 'h2',
          incident_count: 3,
          h2_count: 3,
          h3_count: 0,
          h4_count: 0,
          general_count: 0,
          outcome: 'failed',
          annotated_at: '2026-05-24T00:00:00Z',
        },
      ],
    });
    const w = mount(HarnessLayerCard);
    await flushPromises();

    const recent = w.find('[data-testid="harness-layer-recent"]');
    expect(recent.exists()).toBe(true);
    expect(recent.text()).toContain('exec-zzz');
    expect(recent.text()).toContain('H2');
    expect(recent.text()).toContain('3 incidents');
  });

  it('renders the error stub when the API rejects', async () => {
    getSummary.mockRejectedValue(new Error('boom'));
    const w = mount(HarnessLayerCard);
    await flushPromises();
    expect(w.find('.error-stub').exists()).toBe(true);
  });

  it('exposes the #harness-layers anchor for deep-link scroll', async () => {
    getSummary.mockResolvedValue({
      since: null,
      by_layer: { h2: 0, h3: 0, h4: 0, general: 0, none: 0, total: 0 },
      recent_failures: [],
    });
    const w = mount(HarnessLayerCard);
    await flushPromises();
    expect(w.find('#harness-layers').exists()).toBe(true);
  });
});
