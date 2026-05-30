/**
 * HarnessEvolutionCard — project-scoped Forge evolution surface.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, h } from 'vue';

const { listAll, approve, abort, dryRun, liveRun, getRound, listForProject, projectList } =
  vi.hoisted(() => ({
    listAll: vi.fn(),
    approve: vi.fn(),
    abort: vi.fn(),
    dryRun: vi.fn(),
    liveRun: vi.fn(),
    getRound: vi.fn(),
    listForProject: vi.fn(),
    projectList: vi.fn(),
  }));

vi.mock('../../../../services/api/harness-evolution', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/api/harness-evolution')
  >('../../../../services/api/harness-evolution');
  return {
    ...actual,
    harnessEvolutionApi: { listAll, approve, abort, dryRun, liveRun, getRound, listForProject },
  };
});

vi.mock('../../../../services/api', () => ({
  projectApi: { list: projectList },
}));

vi.mock('../../../../components/base/LoadingState.vue', () => ({
  default: defineComponent({ render: () => h('div', { class: 'loading-stub' }) }),
}));
vi.mock('../../../../components/base/ErrorState.vue', () => ({
  default: defineComponent({ render: () => h('div', { class: 'error-stub' }) }),
}));

import HarnessEvolutionCard from '../HarnessEvolutionCard.vue';

function _round(over: Partial<{ id: string; project_id: string; status: string;
                                entries: Array<{ op: string }> }>) {
  return {
    id: over.id || 'her-aaa',
    project_id: over.project_id || 'proj-x',
    status: over.status || 'awaiting_approval',
    started_at: '2026-05-25T00:00:00Z',
    finished_at: '2026-05-25T00:01:00Z',
    input_window_since: null,
    input_window_until: null,
    input_execution_count: 5,
    input_forge: {},
    output_patch: {
      notes: 'note',
      entries: over.entries || [{ op: 'create', kind: 'rule', name: 'r' }],
    },
    applied_asset_ids: [],
    error_message: null,
    notes: 'codex thought…',
    scratch_dir: null,
  };
}

beforeEach(() => {
  for (const fn of [listAll, approve, abort, dryRun, liveRun, getRound, listForProject, projectList]) {
    fn.mockReset();
  }
  projectList.mockResolvedValue({ projects: [] });
});

describe('HarnessEvolutionCard (project-scoped)', () => {
  it('renders rounds with status pill, project id, and patch summary', async () => {
    listAll.mockResolvedValue({
      rounds: [
        _round({ id: 'her-1', project_id: 'proj-x', status: 'applied',
                 entries: [{ op: 'create' }, { op: 'update' }, { op: 'delete' }] }),
      ],
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    const text = w.text();
    expect(text).toContain('proj-x');
    expect(text).toContain('Applied');
    expect(text).toContain('+1 create');
    expect(text).toContain('~1 update');
    expect(text).toContain('-1 delete');
  });

  it('populates the project picker and pre-selects the first', async () => {
    listAll.mockResolvedValue({ rounds: [] });
    projectList.mockResolvedValue({
      projects: [
        { id: 'proj-a', name: 'Alpha' },
        { id: 'proj-b', name: 'Beta' },
      ],
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    const select = w.find<HTMLSelectElement>(
      '[data-testid="evolution-trigger-project-select"]',
    );
    const options = select.findAll('option');
    expect(options.map((o) => o.attributes('value'))).toEqual(['proj-a', 'proj-b']);
    expect(select.element.value).toBe('proj-a');
  });

  it('dry-run button calls API with project_id and reloads', async () => {
    listAll
      .mockResolvedValueOnce({ rounds: [] })
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-new', project_id: 'proj-a',
                          status: 'awaiting_approval' })],
      });
    projectList.mockResolvedValue({
      projects: [{ id: 'proj-a', name: 'Alpha' }],
    });
    dryRun.mockResolvedValue({
      round_id: 'her-new', status: 'awaiting_approval',
      applied_asset_ids: [], error: null, notes: null,
    });

    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    await w.find('[data-testid="evolution-trigger-dry-run"]').trigger('click');
    await flushPromises();
    expect(dryRun).toHaveBeenCalledWith('proj-a', { limit: 25, force: false });
    expect(listAll).toHaveBeenCalledTimes(2);
    expect(w.find('[data-testid="evolution-round-her-new"]').exists()).toBe(true);
  });

  it('Force checkbox passes force=true to the dry-run API', async () => {
    listAll.mockResolvedValue({ rounds: [] });
    projectList.mockResolvedValue({
      projects: [{ id: 'proj-f', name: 'Force' }],
    });
    dryRun.mockResolvedValue({
      round_id: 'her-f', status: 'awaiting_approval',
      applied_asset_ids: [], error: null, notes: null,
    });

    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    const force = w.find<HTMLInputElement>('[data-testid="evolution-trigger-force"]');
    await force.setValue(true);
    await w.find('[data-testid="evolution-trigger-dry-run"]').trigger('click');
    await flushPromises();
    expect(dryRun).toHaveBeenCalledWith('proj-f', { limit: 25, force: true });
  });

  it('approve + abort call the API and reload', async () => {
    listAll
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-await', status: 'awaiting_approval' })],
      })
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-await', status: 'applied' })],
      });
    approve.mockResolvedValue({
      round_id: 'her-await', status: 'applied',
      applied_asset_ids: [], error: null, notes: null,
    });

    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    await w.find('[data-testid="evolution-approve-her-await"]').trigger('click');
    await flushPromises();
    expect(approve).toHaveBeenCalledWith('her-await');
    expect(w.text()).toContain('Applied');
  });

  it('row click opens the detail modal (and inline approve does NOT bubble)', async () => {
    listAll
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-stop', status: 'awaiting_approval' })],
      })
      .mockResolvedValueOnce({
        rounds: [_round({ id: 'her-stop', status: 'applied' })],
      });
    approve.mockResolvedValue({
      round_id: 'her-stop', status: 'applied',
      applied_asset_ids: [], error: null, notes: null,
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    expect(w.find('[data-testid="evolution-detail-modal"]').exists()).toBe(false);

    await w.find('[data-testid="evolution-approve-her-stop"]').trigger('click');
    await flushPromises();
    // Modal stays closed — @click.stop on the actions block guarantees this.
    expect(w.find('[data-testid="evolution-detail-modal"]').exists()).toBe(false);

    // Now click the row itself → modal opens.
    await w.find('[data-testid="evolution-round-her-stop"]').trigger('click');
    await flushPromises();
    expect(w.find('[data-testid="evolution-detail-modal"]').exists()).toBe(true);
  });

  it('empty state when no rounds', async () => {
    listAll.mockResolvedValue({ rounds: [] });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    expect(w.find('[data-testid="harness-evolution-empty"]').exists()).toBe(true);
  });

  it('error stub when listAll rejects', async () => {
    listAll.mockRejectedValue(new Error('boom'));
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    expect(w.find('.error-stub').exists()).toBe(true);
  });

  it('projectApi.list failure leaves trigger disabled but does not break the card', async () => {
    listAll.mockResolvedValue({ rounds: [] });
    projectList.mockRejectedValue(new Error('500 internal'));
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    expect(w.find('[data-testid="evolution-trigger-section"]').exists()).toBe(true);
    expect(
      w.find<HTMLButtonElement>('[data-testid="evolution-trigger-dry-run"]')
        .attributes('disabled'),
    ).toBeDefined();
  });

  it('renders auto-applied badge for an applied round with auto_applied set', async () => {
    listAll.mockResolvedValue({
      rounds: [
        {
          ..._round({ id: 'her-auto', status: 'applied' }),
          auto_applied: 1,
          auto_apply_reason: { score: 0.95 },
        },
      ],
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    const badge = w.find('[data-testid="auto-applied-badge"]');
    expect(badge.exists()).toBe(true);
    expect(badge.text()).toContain('Auto-applied');
    expect(badge.text()).toContain('0.95');
  });

  it('does not render auto-applied badge for a plain applied round', async () => {
    listAll.mockResolvedValue({
      rounds: [_round({ id: 'her-plain', status: 'applied' })],
    });
    const w = mount(HarnessEvolutionCard);
    await flushPromises();
    expect(w.find('[data-testid="auto-applied-badge"]').exists()).toBe(false);
  });
});
