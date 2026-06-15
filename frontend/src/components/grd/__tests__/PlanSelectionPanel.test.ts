/**
 * PlanSelectionPanel (GRD 0.4.5 multi-candidate selection) — sub-project #3.
 * Mounts in happy-dom, mocks grdPlanningApi, verifies dry-run scoring + promote
 * call the right API and render the ranked candidates / winner / no-candidates.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import enLocale from '../../../locales/en.json';

const calls = vi.hoisted(() => ({
  selectCandidate: vi.fn(),
  getSelection: vi.fn(),
  planTournament: vi.fn(),
}));

vi.mock('../../../services/api', async (orig) => {
  const actual = await orig<typeof import('../../../services/api')>();
  return { ...actual, grdPlanningApi: calls };
});

import PlanSelectionPanel from '../PlanSelectionPanel.vue';

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: { grdPlanSelection: enLocale.grdPlanSelection } } as never,
  });
}
function mountPanel() {
  return mount(PlanSelectionPanel, {
    props: { projectId: 'proj-1', phase: 3 },
    global: { plugins: [makeI18n()] },
  });
}

const RESULT = {
  phase: '3',
  candidates: [
    { relPath: 'phases/03/PLAN-1.md', total_score: 1.1, hard_fail: null },
    { relPath: 'phases/03/PLAN-2.md', total_score: 2.4, hard_fail: null },
  ],
  winner: { relPath: 'phases/03/PLAN-2.md', total_score: 2.4 },
  promoted_to: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  calls.getSelection.mockRejectedValue(new Error('404')); // no prior selection
});

describe('PlanSelectionPanel', () => {
  it('expands and loads any prior selection', async () => {
    const w = mountPanel();
    await w.find('[data-testid="plan-select-toggle-3"]').trigger('click');
    await flushPromises();
    expect(calls.getSelection).toHaveBeenCalledWith('proj-1', 3);
    expect(w.find('[data-testid="plan-select-score-3"]').exists()).toBe(true);
  });

  it('dry-run scoring calls selectCandidate({dry_run:true}) and renders ranked candidates + winner', async () => {
    calls.selectCandidate.mockResolvedValue({ success: true, data: RESULT, error: null, mirrored: null });
    const w = mountPanel();
    await w.find('[data-testid="plan-select-toggle-3"]').trigger('click');
    await flushPromises();
    await w.find('[data-testid="plan-select-score-3"]').trigger('click');
    await flushPromises();
    expect(calls.selectCandidate).toHaveBeenCalledWith('proj-1', 3, { dry_run: true });
    expect(w.text()).toContain('PLAN-1.md');
    expect(w.text()).toContain('PLAN-2.md');
    expect(w.find('.ps-row.winner').exists()).toBe(true);
  });

  it('promote calls selectCandidate({dry_run:false}) and shows promoted path', async () => {
    calls.selectCandidate.mockResolvedValue({
      success: true,
      data: { ...RESULT, promoted_to: 'phases/03/PLAN.md' },
      error: null,
      mirrored: 'psel-abc',
    });
    const w = mountPanel();
    await w.find('[data-testid="plan-select-toggle-3"]').trigger('click');
    await flushPromises();
    await w.find('[data-testid="plan-select-promote-3"]').trigger('click');
    await flushPromises();
    expect(calls.selectCandidate).toHaveBeenCalledWith('proj-1', 3, { dry_run: false });
    expect(w.find('.ps-promoted').text()).toContain('phases/03/PLAN.md');
  });

  it('surfaces the no-candidates error', async () => {
    class ApiErr extends Error {}
    const { ApiError } = await import('../../../services/api');
    calls.selectCandidate.mockRejectedValue(
      new ApiError(400, 'no PLAN-N.md candidates found'),
    );
    void ApiErr;
    const w = mountPanel();
    await w.find('[data-testid="plan-select-toggle-3"]').trigger('click');
    await flushPromises();
    await w.find('[data-testid="plan-select-score-3"]').trigger('click');
    await flushPromises();
    expect(w.find('[data-testid="plan-select-error-3"]').text()).toContain('no PLAN-N.md candidates');
  });
});
