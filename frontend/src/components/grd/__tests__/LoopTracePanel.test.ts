import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import en from '../../../locales/en.json';

const calls = vi.hoisted(() => ({
  listGoalIterations: vi.fn().mockResolvedValue({ iterations: [
    { iteration: 1, verdict: 'not_met', confidence: 0.4, judge_source: 'llm', cost_usd: 0.01, tokens_total: 100 },
    { iteration: 2, verdict: 'met', confidence: 0.9, judge_source: 'llm', cost_usd: 0.02, tokens_total: 200 },
  ] }),
  pauseSession: vi.fn().mockResolvedValue({}), resumeSession: vi.fn().mockResolvedValue({}),
  interveneLoop: vi.fn().mockResolvedValue({}), gateDecision: vi.fn().mockResolvedValue({}),
}));
vi.mock('../../../services/api', async (o) => ({ ...(await o<any>()), grdApi: calls }));
import LoopTracePanel from '../LoopTracePanel.vue';

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: { loopControl: en.loopControl } } as never });
const mountP = (props = {}) => mount(LoopTracePanel, { props: { projectId: 'p', sessionId: 's', awaitingHuman: false, ...props }, global: { plugins: [i18n] } });

describe('LoopTracePanel', () => {
  it('renders the per-iteration trace rows', async () => {
    const w = mountP(); await flushPromises();
    expect(calls.listGoalIterations).toHaveBeenCalledWith('p', 's');
    expect(w.findAll('[data-testid="loop-iter-row"]').length).toBe(2);
  });
  it('pause calls grdApi.pauseSession', async () => {
    const w = mountP(); await flushPromises();
    await w.find('[data-testid="loop-pause"]').trigger('click');
    expect(calls.pauseSession).toHaveBeenCalledWith('p', 's');
  });
  it('shows the gate card and Continue calls gateDecision', async () => {
    const w = mountP({ awaitingHuman: true }); await flushPromises();
    await w.find('[data-testid="gate-continue"]').trigger('click');
    expect(calls.gateDecision).toHaveBeenCalledWith('p', 's', 'continue', undefined);
  });
  it('Modify sends the trimmed gate note', async () => {
    const w = mountP({ awaitingHuman: true }); await flushPromises();
    await w.find('[data-testid="gate-note"]').setValue('  fix the parser  ');
    await w.find('[data-testid="gate-modify"]').trigger('click');
    expect(calls.gateDecision).toHaveBeenCalledWith('p', 's', 'modify', 'fix the parser');
  });
  it('Modify with an empty note coalesces to undefined', async () => {
    const w = mountP({ awaitingHuman: true }); await flushPromises();
    await w.find('[data-testid="gate-modify"]').trigger('click');
    expect(calls.gateDecision).toHaveBeenCalledWith('p', 's', 'modify', undefined);
  });
  it('Abort calls gateDecision with abort', async () => {
    const w = mountP({ awaitingHuman: true }); await flushPromises();
    await w.find('[data-testid="gate-abort"]').trigger('click');
    expect(calls.gateDecision).toHaveBeenCalledWith('p', 's', 'abort', undefined);
  });
});
