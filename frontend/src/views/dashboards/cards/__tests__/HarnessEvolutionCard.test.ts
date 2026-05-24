/**
 * HarnessEvolutionCard — Activity-lane round list with inline approve/abort
 * for ``awaiting_approval`` rounds.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, h } from 'vue';

const { listAll, approve, abort, dryRun, liveRun, getRound, listForBot, triggerList } =
  vi.hoisted(() => ({
    listAll: vi.fn(),
    approve: vi.fn(),
    abort: vi.fn(),
    dryRun: vi.fn(),
    liveRun: vi.fn(),
    getRound: vi.fn(),
    listForBot: vi.fn(),
    triggerList: vi.fn(),
  }));

vi.mock('../../../../services/api/harness-evolution', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/api/harness-evolution')
  >('../../../../services/api/harness-evolution');
  return {
    ...actual,
    harnessEvolutionApi: { listAll, approve, abort, dryRun, liveRun, getRound, listForBot },
  };
});

vi.mock('../../../../services/api', () => ({
  triggerApi: { list: triggerList },
}));

vi.mock('../../../../components/base/LoadingState.vue', () => ({
  default: defineComponent({ render: () => h('div', { class: 'loading-stub' }) }),
}));
vi.mock('../../../../components/base/ErrorState.vue', () => ({
  default: defineComponent({ render: () => h('div', { class: 'error-stub' }) }),
}));

import HarnessEvolutionCard from '../HarnessEvolutionCard.vue';

function _round(over: Partial<{ id: string; bot_id: string; status: string;
                               entries: Array<{ op: string }> }>) {
  return {
    id: over.id || 'her-aaa',
    bot_id: over.bot_id || 'bot-x',
    status: over.status || 'awaiting_approval',
    started_at: '2026-05-24T00:00:00Z',
    finished_at: '2026-05-24T00:01:00Z',
    input_window_since: null,
    input_window_until: null,
    input_execution_count: 5,
    input_layers: {},
    output_patch: {
      notes: 'note',
      entries: over.entries || [{ op: 'create', layer: 'h2', name: 'r' }],
    },
    applied_layer_ids: [],
    error_message: null,
    notes: 'codex thought…',
    scratch_dir: null,
  };
}

beforeEach(() => {
  for (const fn of [listAll, approve, abort, dryRun, liveRun, getRound, listForBot, triggerList]) {
    fn.mockReset();
  }
  // Default: empty bot list. Individual tests override.
  triggerList.mockResolvedValue({ triggers: [] });
});

describe('HarnessEvolutionCard', () => {
  it('renders rounds with status pill, bot id, and patch summary', async () => {
    listAll.mockResolvedValue({
      rounds: [
        _round({ id: 'her-1', bot_id: 'bot-x', status: 'applied',
                 entries: [{ op: 'create' }, { op: 'supersede' }, { op: 'disable' }] }),
      ],
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    expect(listAll).toHaveBeenCalledWith({ limit: 10 });

    const text = w.text();
    expect(text).toContain('bot-x');
    expect(text).toContain('Applied');
    expect(text).toContain('+1 create');
    expect(text).toContain('~1 supersede');
    expect(text).toContain('-1 disable');
  });

  it('renders approve/abort buttons only on awaiting_approval rounds', async () => {
    listAll.mockResolvedValue({
      rounds: [
        _round({ id: 'her-await', status: 'awaiting_approval' }),
        _round({ id: 'her-done', status: 'applied' }),
      ],
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();

    expect(w.find('[data-testid="evolution-approve-her-await"]').exists()).toBe(true);
    expect(w.find('[data-testid="evolution-abort-her-await"]').exists()).toBe(true);
    expect(w.find('[data-testid="evolution-approve-her-done"]').exists()).toBe(false);
    expect(w.find('[data-testid="evolution-abort-her-done"]').exists()).toBe(false);
  });

  it('clicking Approve calls the API and reloads the list', async () => {
    listAll
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-await', status: 'awaiting_approval' })],
      })
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-await', status: 'applied' })],
      });
    approve.mockResolvedValue({
      round_id: 'her-await', status: 'applied',
      applied_layer_ids: ['hl-x'], error: null, notes: null,
    });

    const w = mount(HarnessEvolutionCard);
    await flushPromises();

    await w.find('[data-testid="evolution-approve-her-await"]').trigger('click');
    await flushPromises();

    expect(approve).toHaveBeenCalledWith('her-await');
    expect(listAll).toHaveBeenCalledTimes(2);  // initial + reload after approve
    // After reload, the awaiting-approval pill is gone.
    expect(w.text()).toContain('Applied');
    expect(w.find('[data-testid="evolution-approve-her-await"]').exists()).toBe(false);
  });

  it('clicking Abort sends reason and reloads', async () => {
    listAll
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-x', status: 'awaiting_approval' })],
      })
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-x', status: 'aborted' })],
      });
    abort.mockResolvedValue({
      round_id: 'her-x', status: 'aborted',
      applied_layer_ids: [], error: null, notes: null,
    });

    const w = mount(HarnessEvolutionCard);
    await flushPromises();

    await w.find('[data-testid="evolution-abort-her-x"]').trigger('click');
    await flushPromises();

    expect(abort).toHaveBeenCalledWith('her-x', 'operator rejected');
    expect(w.text()).toContain('Aborted');
  });

  it('surfaces an approve API failure in the action-error region', async () => {
    listAll.mockResolvedValue({
      rounds: [_round({ id: 'her-fail', status: 'awaiting_approval' })],
    });
    approve.mockResolvedValue({
      round_id: 'her-fail', status: 'failed',
      applied_layer_ids: [], error: 'apply errored', notes: null,
    });

    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    await w.find('[data-testid="evolution-approve-her-fail"]').trigger('click');
    await flushPromises();

    expect(w.find('[role="alert"]').text()).toContain('apply errored');
  });

  it('shows the empty state when no rounds have been recorded', async () => {
    listAll.mockResolvedValue({ rounds: [] });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    expect(w.find('[data-testid="harness-evolution-empty"]').exists()).toBe(true);
  });

  it('renders the error stub on API failure', async () => {
    listAll.mockRejectedValue(new Error('boom'));
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    expect(w.find('.error-stub').exists()).toBe(true);
  });

  it('exposes the #harness-evolution anchor for deep-link scroll', async () => {
    listAll.mockResolvedValue({ rounds: [] });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    expect(w.find('#harness-evolution').exists()).toBe(true);
  });

  it('clicking a round opens the detail modal with that round', async () => {
    listAll.mockResolvedValue({
      rounds: [_round({ id: 'her-detail', status: 'applied' })],
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    // Modal hidden before click.
    expect(w.find('[data-testid="evolution-detail-modal"]').exists()).toBe(false);
    await w.find('[data-testid="evolution-round-her-detail"]').trigger('click');
    await flushPromises();
    expect(w.find('[data-testid="evolution-detail-modal"]').exists()).toBe(true);
    // The modal received the round that was clicked.
    expect(w.text()).toContain('her-detail');
  });

  it('inline approve button does NOT bubble up to open the modal', async () => {
    listAll
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-stop', status: 'awaiting_approval' })],
      })
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-stop', status: 'applied' })],
      });
    approve.mockResolvedValue({
      round_id: 'her-stop', status: 'applied',
      applied_layer_ids: [], error: null, notes: null,
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    await w.find('[data-testid="evolution-approve-her-stop"]').trigger('click');
    await flushPromises();
    // Modal must NOT have opened — the click.stop on the actions block
    // is what guarantees this.
    expect(w.find('[data-testid="evolution-detail-modal"]').exists()).toBe(false);
  });

  // --------------------------------------------------------------------
  // Trigger form
  // --------------------------------------------------------------------

  it('populates the bot picker from triggerApi.list and pre-selects the first', async () => {
    listAll.mockResolvedValue({ rounds: [] });
    triggerList.mockResolvedValue({
      triggers: [
        { id: 'bot-a', name: 'Alpha' },
        { id: 'bot-b', name: 'Beta' },
      ],
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();

    const select = w.find<HTMLSelectElement>(
      '[data-testid="evolution-trigger-bot-select"]',
    );
    expect(select.exists()).toBe(true);
    const options = select.findAll('option');
    // Both bots present (no "No bots" placeholder when list is non-empty).
    expect(options.map((o) => o.attributes('value'))).toEqual(['bot-a', 'bot-b']);
    expect(select.element.value).toBe('bot-a');
  });

  it('Dry-run button is disabled until a bot is selectable', async () => {
    listAll.mockResolvedValue({ rounds: [] });
    triggerList.mockResolvedValue({ triggers: [] });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    const btn = w.find<HTMLButtonElement>(
      '[data-testid="evolution-trigger-dry-run"]',
    );
    expect(btn.attributes('disabled')).toBeDefined();
  });

  it('Dry-run click calls the API and reloads the list', async () => {
    listAll
      .mockResolvedValueOnce({ rounds: [] })
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-new', status: 'awaiting_approval' })],
      });
    triggerList.mockResolvedValue({
      triggers: [{ id: 'bot-x', name: 'X' }],
    });
    dryRun.mockResolvedValue({
      round_id: 'her-new',
      status: 'awaiting_approval',
      applied_layer_ids: [],
      error: null,
      notes: null,
    });

    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    await w.find('[data-testid="evolution-trigger-dry-run"]').trigger('click');
    await flushPromises();

    expect(dryRun).toHaveBeenCalledWith('bot-x', { limit: 25 });
    // List was reloaded after the trigger fired.
    expect(listAll).toHaveBeenCalledTimes(2);
    const status = w.find('[data-testid="evolution-trigger-status"]');
    expect(status.exists()).toBe(true);
    expect(status.text()).toContain('her-new');
    expect(status.text()).toContain('awaiting_approval');
    // The new round shows up in the list.
    expect(w.find('[data-testid="evolution-round-her-new"]').exists()).toBe(true);
  });

  it('surfaces a failed dry-run in the trigger error region', async () => {
    listAll.mockResolvedValue({ rounds: [] });
    triggerList.mockResolvedValue({
      triggers: [{ id: 'bot-fail', name: 'F' }],
    });
    dryRun.mockResolvedValue({
      round_id: 'her-fail',
      status: 'failed',
      applied_layer_ids: [],
      error: 'codex CLI not found',
      notes: null,
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    await w.find('[data-testid="evolution-trigger-dry-run"]').trigger('click');
    await flushPromises();
    const err = w.find('[data-testid="evolution-trigger-error"]');
    expect(err.exists()).toBe(true);
    expect(err.text()).toContain('codex CLI not found');
  });

  it('triggerApi.list failure does not break the card; bot picker stays empty', async () => {
    listAll.mockResolvedValue({ rounds: [] });
    triggerList.mockRejectedValue(new Error('500 internal'));
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    // Card renders, trigger section exists, button is disabled because no bots.
    expect(w.find('[data-testid="evolution-trigger-section"]').exists()).toBe(true);
    expect(
      w.find<HTMLButtonElement>('[data-testid="evolution-trigger-dry-run"]')
        .attributes('disabled'),
    ).toBeDefined();
  });
});
