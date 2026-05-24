/**
 * HarnessEvolutionDetailModal — full per-entry payload view + impact metrics.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

const { getImpact } = vi.hoisted(() => ({ getImpact: vi.fn() }));

vi.mock('../../../../services/api/harness-evolution', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/api/harness-evolution')
  >('../../../../services/api/harness-evolution');
  return {
    ...actual,
    harnessEvolutionApi: {
      getImpact,
      listAll: vi.fn(),
      approve: vi.fn(),
      abort: vi.fn(),
      dryRun: vi.fn(),
      liveRun: vi.fn(),
      getRound: vi.fn(),
      listForBot: vi.fn(),
    },
  };
});

import HarnessEvolutionDetailModal from '../HarnessEvolutionDetailModal.vue';

function _round(over: Partial<{ id: string; status: string;
                                entries: Array<Record<string, unknown>>;
                                notes: string | null;
                                error_message: string | null }>) {
  return {
    id: over.id || 'her-x',
    bot_id: 'bot-x',
    status: over.status || 'applied',
    started_at: '2026-05-25T00:00:00Z',
    finished_at: '2026-05-25T00:01:00Z',
    input_window_since: null,
    input_window_until: null,
    input_execution_count: 4,
    input_layers: {},
    output_patch: {
      notes: '',
      entries: (over.entries as Array<Record<string, unknown>> | undefined) || [
        {
          op: 'create', layer: 'h2', name: 'block-rm',
          existing_layer_id: null,
          payload: { title: 'Block rm', action: { kind: 'block' } },
        },
      ],
    },
    applied_layer_ids: [],
    error_message: over.error_message ?? null,
    notes: over.notes ?? 'Codex saw 3 recurring rm attempts.',
    scratch_dir: null,
  };
}

beforeEach(() => {
  getImpact.mockReset();
});

describe('HarnessEvolutionDetailModal', () => {
  it('does not render when round is null', () => {
    const w = mount(HarnessEvolutionDetailModal, { props: { round: null } });
    expect(w.find('[data-testid="evolution-detail-modal"]').exists()).toBe(false);
  });

  it('renders patch entries with op, layer, name, and payload JSON', async () => {
    getImpact.mockResolvedValue({ available: false, reason: 'noop' });
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({ entries: [
        { op: 'create', layer: 'h2', name: 'block-rm',
          existing_layer_id: null,
          payload: { title: 'Block rm -rf' } },
        { op: 'supersede', layer: 'h3', name: 'quote-cols',
          existing_layer_id: 'hl-abc',
          payload: { title: 'Quote cols v2' } },
      ] }) },
    });
    await flushPromises();
    const entries = w.findAll('[data-testid^="evolution-entry-"]');
    expect(entries).toHaveLength(2);
    expect(entries[0].text()).toContain('create');
    expect(entries[0].text()).toContain('H2');
    expect(entries[0].text()).toContain('Block rm -rf');
    expect(entries[1].text()).toContain('supersede');
    expect(entries[1].text()).toContain('hl-abc');
  });

  it('shows Codex notes and error message when present', async () => {
    getImpact.mockResolvedValue({ available: false, reason: 'noop' });
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({
        status: 'failed', notes: 'tried hard', error_message: 'codex 1: boom',
      }) },
    });
    await flushPromises();
    expect(w.find('[data-testid="evolution-detail-notes"]').text()).toBe('tried hard');
    expect(w.find('[data-testid="evolution-detail-error"]').text()).toContain('boom');
  });

  it('fetches impact for applied rounds and renders the delta', async () => {
    getImpact.mockResolvedValue({
      available: true,
      round_id: 'her-x', bot_id: 'bot-x', window_size: 20,
      before: { executions: 10, success_rate: 0.4,
                failure_layers: { h2: 6, h3: 0, h4: 0, general: 0 },
                mean_incident_count: 2 },
      after: { executions: 10, success_rate: 0.8,
               failure_layers: { h2: 2, h3: 0, h4: 0, general: 0 },
               mean_incident_count: 1 },
      delta: { success_rate: 0.4, mean_incident_count: -1,
               failure_layers: { h2: -4, h3: 0, h4: 0, general: 0 } },
    });
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({ status: 'applied' }) },
    });
    await flushPromises();
    expect(getImpact).toHaveBeenCalledWith('her-x');
    const section = w.find('[data-testid="evolution-impact-section"]');
    expect(section.text()).toContain('40.0%');
    expect(section.text()).toContain('80.0%');
    const delta = w.find('[data-testid="evolution-impact-delta"]');
    expect(delta.text()).toContain('+40.0pp');
    expect(delta.classes()).toContain('pos');
  });

  it('does not fetch impact for non-applied rounds', async () => {
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({ status: 'awaiting_approval' }) },
    });
    await flushPromises();
    expect(getImpact).not.toHaveBeenCalled();
    expect(w.find('[data-testid="evolution-impact-section"]').exists()).toBe(false);
  });

  it('shows reason when impact endpoint returns available:false', async () => {
    getImpact.mockResolvedValue({ available: false, reason: 'no data yet' });
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({ status: 'applied' }) },
    });
    await flushPromises();
    const section = w.find('[data-testid="evolution-impact-section"]');
    expect(section.text()).toContain('no data yet');
  });

  it('shows approve/abort only on awaiting_approval and emits events', async () => {
    getImpact.mockResolvedValue({ available: false, reason: 'noop' });
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({ id: 'her-aa', status: 'awaiting_approval' }) },
    });
    await flushPromises();
    expect(w.find('[data-testid="evolution-detail-approve"]').exists()).toBe(true);
    await w.find('[data-testid="evolution-detail-approve"]').trigger('click');
    expect(w.emitted('approve')).toEqual([['her-aa']]);

    await w.find('[data-testid="evolution-detail-abort"]').trigger('click');
    expect(w.emitted('abort')).toEqual([['her-aa']]);
  });

  it('close button emits close', async () => {
    getImpact.mockResolvedValue({ available: false, reason: 'noop' });
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({ status: 'applied' }) },
    });
    await flushPromises();
    await w.find('[data-testid="evolution-detail-close"]').trigger('click');
    expect(w.emitted('close')).toBeTruthy();
  });

  it('clicking the dark backdrop emits close; clicking the panel does not', async () => {
    getImpact.mockResolvedValue({ available: false, reason: 'noop' });
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({ status: 'applied' }) },
    });
    await flushPromises();
    // Click inside panel — should NOT close.
    await w.find('.modal-panel').trigger('click');
    expect(w.emitted('close')).toBeUndefined();
    // Click backdrop — SHOULD close.
    await w.find('.modal-backdrop').trigger('click');
    expect(w.emitted('close')).toBeTruthy();
  });
});
