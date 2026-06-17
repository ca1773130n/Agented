/**
 * GenomePanel pattern-mining section (GRD 0.4.1 → GENOME-SUGGESTIONS) — #4.
 * Mounts in happy-dom, mocks grdHarnessApi, verifies Mine renders suggestions
 * and Promote calls promoteSuggestion with the `<token>-rate` slug.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import enLocale from '../../../../../locales/en.json';

const calls = vi.hoisted(() => ({
  getGenome: vi.fn().mockResolvedValue({ exists: false }),
  latestGenomeSnapshot: vi.fn().mockResolvedValue({}),
  listGenomeSnapshots: vi.fn().mockResolvedValue({ snapshots: [] }),
  snapshotGenome: vi.fn().mockResolvedValue({}),
  minePatterns: vi.fn(),
  getGenomeSuggestions: vi.fn(),
  promoteSuggestion: vi.fn().mockResolvedValue({ success: true, data: {}, error: null }),
}));

vi.mock('../../../../../services/api', async (orig) => {
  const actual = await orig<typeof import('../../../../../services/api')>();
  return { ...actual, grdHarnessApi: calls };
});

import GenomePanel from '../GenomePanel.vue';

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: { surface: enLocale.surface } } as never,
  });
}
function mountPanel() {
  return mount(GenomePanel, {
    props: { projectId: 'proj-1' },
    global: { plugins: [makeI18n()] },
  });
}

const MINED = {
  success: true,
  data: {
    reflections_scanned: 12,
    baseline_confirmed_rate: 0.5,
    tokens_tested: 30,
    suggestions: [
      { token: 'refactor', n: 11, confirmed: 9, confirmed_rate: 0.82, baseline: 0.5,
        effect_size: 0.32, raw_p: 0.01, fdr_q: 0.04, significant: true },
    ],
    applied: true,
    suggestions_path: '.planning/GENOME-SUGGESTIONS.md',
  },
  error: null,
  mirrored: 'gsug-1',
};

beforeEach(() => {
  vi.clearAllMocks();
  calls.getGenome.mockResolvedValue({ exists: false });
  calls.latestGenomeSnapshot.mockResolvedValue({});
  calls.listGenomeSnapshots.mockResolvedValue({ snapshots: [] });
  calls.getGenomeSuggestions.mockRejectedValue(new Error('404')); // no prior run
  calls.promoteSuggestion.mockResolvedValue({ success: true, data: {}, error: null });
});

describe('GenomePanel — pattern mining', () => {
  it('Mine & save calls minePatterns({apply:true}) and lists suggestions', async () => {
    calls.minePatterns.mockResolvedValue(MINED);
    const w = mountPanel();
    await flushPromises();
    await w.find('[data-testid="patterns-save"]').trigger('click');
    await flushPromises();
    expect(calls.minePatterns).toHaveBeenCalledWith('proj-1', { apply: true });
    expect(w.text()).toContain('refactor');
  });

  it('Promote calls promoteSuggestion with <token>-rate once suggestions saved', async () => {
    calls.minePatterns.mockResolvedValue(MINED);
    const w = mountPanel();
    await flushPromises();
    await w.find('[data-testid="patterns-save"]').trigger('click');
    await flushPromises();
    await w.find('[data-testid="patterns-promote-refactor"]').trigger('click');
    await flushPromises();
    expect(calls.promoteSuggestion).toHaveBeenCalledWith('proj-1', 'refactor-rate');
  });

  it('preview (no save) leaves Promote disabled', async () => {
    calls.minePatterns.mockResolvedValue({ ...MINED, data: { ...MINED.data, applied: false } });
    const w = mountPanel();
    await flushPromises();
    await w.find('[data-testid="patterns-mine"]').trigger('click');
    await flushPromises();
    expect(calls.minePatterns).toHaveBeenCalledWith('proj-1', { apply: false });
    const btn = w.find('[data-testid="patterns-promote-refactor"]');
    expect(btn.attributes('disabled')).toBeDefined();
  });
});
