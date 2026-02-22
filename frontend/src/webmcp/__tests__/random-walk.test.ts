/**
 * Random walk test: navigates randomly across pages, invokes random tools on each.
 *
 * Uses a mock tool map simulating registered tools across multiple pages.
 * Validates the random runner engine, weighted selection, and state verification.
 */
import { describe, it, expect, vi } from 'vitest';
import { runRandomWalk } from '../test-harness/random-runner';
import { selectWeightedTool, getToolWeight } from '../test-harness/tool-weights';

function createMockToolMap() {
  const tools = new Map<string, { execute: (a: Record<string, unknown>) => Promise<unknown>; inputSchema?: Record<string, unknown> }>();

  // Simulate tools from multiple pages
  const pageTools = [
    'hive_teams_get_list_state',
    'hive_teams_get_modal_state',
    'hive_teams_trigger_create',
    'hive_agents_get_list_state',
    'hive_agents_get_modal_state',
    'hive_agents_perform_search',
    'hive_agents_perform_sort',
    'hive_agent_design_get_state',
    'hive_dashboards_get_state',
    'hive_settings_get_state',
    'hive_settings_switch_tab',
    'hive_get_page_info',
    'hive_list_registered_tools',
    'hive_sidebar_get_state',
  ];

  for (const name of pageTools) {
    const inputSchema: Record<string, unknown> = { type: 'object', properties: {} };

    if (name === 'hive_agents_perform_search') {
      inputSchema.properties = { query: { type: 'string' } };
      inputSchema.required = ['query'];
    } else if (name === 'hive_agents_perform_sort') {
      inputSchema.properties = { field: { type: 'string' }, order: { type: 'string' } };
      inputSchema.required = ['field', 'order'];
    } else if (name === 'hive_settings_switch_tab') {
      inputSchema.properties = { tab: { type: 'string' } };
      inputSchema.required = ['tab'];
    }

    tools.set(name, {
      inputSchema,
      execute: vi.fn(async () => ({
        content: [{ type: 'text', text: JSON.stringify({ page: 'mock', success: true }) }],
      })),
    });
  }

  return tools;
}

describe('random-walk', () => {
  it('completes a random walk with 20 iterations without aborting', async () => {
    const toolMap = createMockToolMap();
    const report = await runRandomWalk(toolMap, {
      maxIterations: 20,
      delayMs: 0,
    });

    expect(report.abortedEarly).toBe(false);
    expect(report.totalInvocations).toBeGreaterThanOrEqual(20);
    expect(report.successes).toBeGreaterThan(0);
    expect(report.failures).toBe(0);
    expect(report.durationMs).toBeGreaterThanOrEqual(0);
  });

  it('tracks tool coverage across invocations', async () => {
    const toolMap = createMockToolMap();
    const report = await runRandomWalk(toolMap, {
      maxIterations: 50,
      delayMs: 0,
    });

    expect(report.toolCoverage.size).toBeGreaterThan(1);
    const totalCoverage = Array.from(report.toolCoverage.values()).reduce((a, b) => a + b, 0);
    expect(totalCoverage).toBe(report.totalInvocations);
  });

  it('aborts on consecutive errors', async () => {
    const failingMap = new Map<string, { execute: (a: Record<string, unknown>) => Promise<unknown>; inputSchema?: Record<string, unknown> }>();
    failingMap.set('hive_test_get_state', {
      execute: vi.fn(async () => { throw new Error('test failure'); }),
    });

    const report = await runRandomWalk(failingMap, {
      maxIterations: 10,
      delayMs: 0,
      maxConsecutiveErrors: 3,
    });

    expect(report.abortedEarly).toBe(true);
    expect(report.failures).toBe(3);
    expect(report.errors).toHaveLength(3);
  });

  it('excludes destructive tools by default', () => {
    const names = ['hive_teams_get_list_state', 'hive_teams_trigger_delete'];
    const selections = new Set<string>();

    for (let i = 0; i < 100; i++) {
      const selected = selectWeightedTool(names, { allowDestructive: false });
      if (selected) selections.add(selected);
    }

    expect(selections.has('hive_teams_trigger_delete')).toBe(false);
    expect(selections.has('hive_teams_get_list_state')).toBe(true);
  });

  it('includes destructive tools when opted in', () => {
    const names = ['hive_teams_trigger_delete'];
    // trigger_delete has weight 0 by default, so it's still excluded even with allowDestructive
    expect(selectWeightedTool(names, { allowDestructive: true })).toBeNull();
    // Override weight to include it
    const selected2 = selectWeightedTool(names, {
      allowDestructive: true,
      weights: [{ pattern: '*_trigger_delete', weight: 10, destructive: true }],
    });
    expect(selected2).toBe('hive_teams_trigger_delete');
  });

  it('state tools have higher weight than action tools', () => {
    const stateWeight = getToolWeight('hive_teams_get_list_state');
    const actionWeight = getToolWeight('hive_teams_trigger_create');

    expect(stateWeight.weight).toBeGreaterThan(actionWeight.weight);
    expect(stateWeight.destructive).toBe(false);
  });

  it('verifies state after action tools', async () => {
    const toolMap = new Map<string, { execute: (a: Record<string, unknown>) => Promise<unknown>; inputSchema?: Record<string, unknown> }>();

    toolMap.set('hive_teams_trigger_create', {
      execute: vi.fn(async () => ({
        content: [{ type: 'text', text: JSON.stringify({ success: true }) }],
      })),
    });
    toolMap.set('hive_teams_get_modal_state', {
      execute: vi.fn(async () => ({
        content: [{ type: 'text', text: JSON.stringify({ showCreateModal: true }) }],
      })),
    });

    const report = await runRandomWalk(toolMap, {
      maxIterations: 5,
      delayMs: 0,
      weights: [{ pattern: '*_trigger_create', weight: 100 }, { pattern: '*_get_modal_state', weight: 1 }],
    });

    expect(report.verifications.length).toBeGreaterThan(0);
    for (const v of report.verifications) {
      expect(v.verified).toBe(true);
    }
  });
});
