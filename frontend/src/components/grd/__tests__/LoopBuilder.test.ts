import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import en from '../../../locales/en.json';
const calls = vi.hoisted(() => ({
  createSession: vi.fn().mockResolvedValue({ session_id: 'gls-1', pid: 1, status: 'active' }),
  createRalphSession: vi.fn().mockResolvedValue({ session_id: 'ralph-1', pid: 1, status: 'active' }),
  listAllowedAccounts: vi.fn().mockResolvedValue({ allowed_accounts: [{ account_id: 'acc-1', created_at: '' }] }),
}));
vi.mock('../../../services/api', async (o) => ({ ...(await o<any>()), grdApi: calls, ApiError: class extends Error {} }));
import LoopBuilder from '../LoopBuilder.vue';
const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: { loopBuilder: en.loopBuilder, loopConfig: en.loopConfig } } as never });
const mountP = (props = {}) => mount(LoopBuilder, { props: { projectId: 'p', cwd: '/w', ...props }, global: { plugins: [i18n], provide: { showToast: vi.fn() } } });
beforeEach(() => vi.clearAllMocks());

describe('LoopBuilder', () => {
  it('launch is disabled until goal is set, then POSTs createSession for a goal-loop template', async () => {
    const w = mountP(); await flushPromises();
    await w.find('[data-testid="tpl-eval_refine"]').trigger('click');
    expect(w.find('[data-testid="lb-launch"]').attributes('disabled')).toBeDefined();
    await w.find('[data-testid="lb-goal"]').setValue('make tests pass');
    await w.find('[data-testid="lb-launch"]').trigger('click'); await flushPromises();
    expect(calls.createSession).toHaveBeenCalledTimes(1);
    const [pid, req] = calls.createSession.mock.calls[0];
    expect(pid).toBe('p');
    expect(req.cmd[0]).toBe('claude');           // route requires a non-empty cmd
    expect(req.execution_type).toBe('goal_loop');
    expect(req.account_id).toBe('acc-1');         // first allowed account auto-selected
    expect(req.goal_loop_config.goal).toBe('make tests pass');
    expect(req.goal_loop_config.quality_gate.kind).toBe('llm_judge');
    expect(w.emitted('launched')![0]).toEqual(['gls-1']);
  });
  it('agentic_task template POSTs createRalphSession with ralph_config', async () => {
    const w = mountP(); await flushPromises();
    await w.find('[data-testid="tpl-agentic_task"]').trigger('click');
    await w.find('[data-testid="lb-task"]').setValue('build the widget');
    await w.find('[data-testid="lb-launch"]').trigger('click'); await flushPromises();
    expect(calls.createRalphSession).toHaveBeenCalledTimes(1);
    const [, req] = calls.createRalphSession.mock.calls[0];
    expect(req.ralph_config.task_description).toBe('build the widget');
    expect(req.ralph_config.no_progress_threshold).toBe(3);
  });
  it('human_gate=every_n includes mode+n in the goal_loop_config', async () => {
    const w = mountP(); await flushPromises();
    await w.find('[data-testid="tpl-custom"]').trigger('click');
    await w.find('[data-testid="lb-goal"]').setValue('g');
    await w.find('[data-testid="lb-human-gate"]').setValue('every_n');
    await w.find('[data-testid="lb-gate-n"]').setValue('3');
    await w.find('[data-testid="lb-launch"]').trigger('click'); await flushPromises();
    const [, req] = calls.createSession.mock.calls[0];
    expect(req.goal_loop_config.human_gate).toEqual({ mode: 'every_n', n: 3 });
  });
});
