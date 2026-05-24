/**
 * HarnessEvolutionDetailModal — full Forge patch view + impact metrics.
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
      listAll: vi.fn(), approve: vi.fn(), abort: vi.fn(),
      dryRun: vi.fn(), liveRun: vi.fn(), getRound: vi.fn(),
      listForProject: vi.fn(),
    },
  };
});

import HarnessEvolutionDetailModal from '../HarnessEvolutionDetailModal.vue';
import type {
  EvolutionPatchEntry,
  EvolutionRound,
  EvolutionStatus,
} from '../../../../services/api/harness-evolution';

function _round(over: Partial<{
  id: string;
  status: EvolutionStatus;
  entries: EvolutionPatchEntry[];
  notes: string | null;
  error_message: string | null;
}>): EvolutionRound {
  return {
    id: over.id || 'her-x',
    project_id: 'proj-x',
    status: over.status || 'applied',
    started_at: '2026-05-25T00:00:00Z',
    finished_at: '2026-05-25T00:01:00Z',
    input_window_since: null,
    input_window_until: null,
    input_execution_count: 4,
    input_forge: {},
    output_patch: {
      notes: '',
      entries: over.entries || [
        {
          op: 'create', kind: 'rule', name: 'quote-cols',
          existing_asset_id: null,
          payload: { description: 'Quote spaced cols' },
        },
      ],
    },
    applied_asset_ids: [],
    error_message: over.error_message ?? null,
    notes: over.notes ?? 'Codex saw recurring SQL quoting issues.',
    scratch_dir: null,
  };
}

beforeEach(() => {
  getImpact.mockReset();
});

describe('HarnessEvolutionDetailModal (Forge edition)', () => {
  it('does not render when round is null', () => {
    const w = mount(HarnessEvolutionDetailModal, { props: { round: null } });
    expect(w.find('[data-testid="evolution-detail-modal"]').exists()).toBe(false);
  });

  it('renders entries with op, kind, name, and payload', async () => {
    getImpact.mockResolvedValue({ available: false, reason: 'noop' });
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({ entries: [
        { op: 'create', kind: 'rule', name: 'quote-cols',
          existing_asset_id: null,
          payload: { description: 'Quote spaced cols' } },
        { op: 'update', kind: 'hook', name: 'block-rm',
          existing_asset_id: 42,
          payload: { event: 'PreToolUse', content: 'sh' } },
        { op: 'delete', kind: 'command', name: 'old-cmd',
          existing_asset_id: 7, payload: null },
      ] }) },
    });
    await flushPromises();
    const entries = w.findAll('[data-testid^="evolution-entry-"]');
    expect(entries).toHaveLength(3);
    expect(entries[0].text()).toContain('create');
    expect(entries[0].text()).toContain('rule');
    expect(entries[0].text()).toContain('Quote spaced cols');
    expect(entries[1].text()).toContain('update');
    expect(entries[1].text()).toContain('hook');
    expect(entries[1].text()).toContain('#42');
    expect(entries[2].text()).toContain('delete');
    expect(entries[2].text()).toContain('command');
  });

  it('renders notes and error', async () => {
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

  it('fetches impact for applied rounds and renders delta', async () => {
    getImpact.mockResolvedValue({
      available: true,
      round_id: 'her-x', project_id: 'proj-x', window_size: 20,
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

  it('approve / abort emit events on awaiting_approval', async () => {
    getImpact.mockResolvedValue({ available: false, reason: 'noop' });
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({ id: 'her-aa', status: 'awaiting_approval' }) },
    });
    await flushPromises();
    await w.find('[data-testid="evolution-detail-approve"]').trigger('click');
    expect(w.emitted('approve')).toEqual([['her-aa']]);
    await w.find('[data-testid="evolution-detail-abort"]').trigger('click');
    expect(w.emitted('abort')).toEqual([['her-aa']]);
  });

  it('close button + backdrop click emit close; panel click does not', async () => {
    getImpact.mockResolvedValue({ available: false, reason: 'noop' });
    const w = mount(HarnessEvolutionDetailModal, {
      props: { round: _round({ status: 'applied' }) },
    });
    await flushPromises();
    await w.find('.modal-panel').trigger('click');
    expect(w.emitted('close')).toBeUndefined();
    await w.find('[data-testid="evolution-detail-close"]').trigger('click');
    expect(w.emitted('close')).toBeTruthy();
  });
});
