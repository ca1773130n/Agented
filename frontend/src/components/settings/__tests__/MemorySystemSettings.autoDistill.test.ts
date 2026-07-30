import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

// The automatic super-agent distill spends LLM calls without an operator in the
// loop, so the settings row is the audit trail. The one thing it must never do
// is present an UNKNOWN spend as an exact figure: a run killed at the 1800 s
// timeout only reports what the agents that finished printed, and the agent it
// killed mid-flight never printed anything.

const api = vi.hoisted(() => ({
  list: vi.fn(),
  listTesseraeProjects: vi.fn(),
}));
vi.mock('../../../services/api/memory-system', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  memorySystemApi: api,
}));

import MemorySystemSettings from '../MemorySystemSettings.vue';

type AutoDistill = {
  at?: string | null;
  reason?: string | null;
  llm_calls?: number | null;
  llm_calls_partial?: boolean;
};

async function noteFor(last_auto_distill: AutoDistill) {
  api.list.mockResolvedValue({
    memory_systems: [
      {
        id: 'tesserae',
        name: 'Tesserae',
        summary: 'Per-project knowledge graph',
        cli: { installed: true, version: '0.28.2', path: '/usr/local/bin/tesserae' },
        enabled_project_count: 1,
      },
    ],
  });
  api.listTesseraeProjects.mockResolvedValue({
    projects: [
      {
        project_id: 'proj-1',
        project_name: 'P1',
        local_path: '/tmp/p1',
        tesserae_project_root: '/tmp/p1',
        enabled: true,
        distill_enabled: true,
        last_auto_distill,
        workspace_initialized: true,
        session_count: 3,
        last_imported_at: null,
      },
    ],
  });
  const w = mount(MemorySystemSettings);
  await flushPromises();
  return w.find('[data-testid="tesserae-auto-distill-proj-1"]');
}

describe('MemorySystemSettings — automatic-distill spend note', () => {
  it('renders a completed run’s cost as an exact number', async () => {
    const note = await noteFor({ at: '2026-07-29T10:00:00Z', reason: 'ok', llm_calls: 17 });
    expect(note.exists()).toBe(true);
    expect(note.text()).toContain('17 provider calls');
    expect(note.text()).not.toContain('≥');
  });

  it('renders a timed-out run’s cost as a floor, never as the total', async () => {
    // Same 17, but the run was killed — so 17 is a lower bound and the reason
    // has to stay visible next to it. Dropping `llm_calls_partial` from
    // `autoDistillCalls` makes this identical to the test above.
    const note = await noteFor({
      at: '2026-07-29T10:00:00Z',
      reason: 'timeout_after_1800s',
      llm_calls: 17,
      llm_calls_partial: true,
    });
    expect(note.text()).toContain('≥17 provider calls');
    expect(note.text()).toContain('timeout_after_1800s');
  });

  it('renders a refusal as a real zero rather than an unknown', async () => {
    // A refusal never spawned tesserae. Showing "—" here would tell the
    // operator we lost track of an automatic bill that was never incurred.
    const note = await noteFor({
      at: '2026-07-29T10:00:00Z',
      reason: 'estimate_over_budget_999',
      llm_calls: 0,
    });
    expect(note.text()).toContain('0 provider calls');
    expect(note.text()).toContain('estimate_over_budget_999');
  });

  it('shows nothing at all until an automatic distill has fired', async () => {
    expect((await noteFor({})).exists()).toBe(false);
  });
});
