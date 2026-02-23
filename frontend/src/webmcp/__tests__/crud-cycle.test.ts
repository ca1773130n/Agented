/**
 * CRUD cycle test: for each entity type, exercises the list → read → create modal → verify flow.
 *
 * Uses mock tool maps to simulate the full CRUD cycle without actual API calls.
 */
import { describe, it, expect, vi } from 'vitest';
import { invokeTool, generateRandomInputs } from '../test-harness/random-runner';
import { getStateToolForAction } from '../test-harness/state-verifier';

const DOMAINS = [
  'teams', 'products', 'projects', 'agents', 'plugins',
  'hooks', 'commands', 'rules', 'mcp_servers', 'super_agents',
  'workflows', 'skills',
];

function createDomainToolMap(domain: string) {
  const tools = new Map<string, { execute: (a: Record<string, unknown>) => Promise<unknown>; inputSchema?: Record<string, unknown> }>();

  const listState = { items: [{ id: `${domain}-001`, name: 'Test' }], itemCount: 1, isLoading: false, error: null };
  const modalClosed = { showCreateModal: false, showDeleteConfirm: false, formValues: {} };
  const modalOpen = { showCreateModal: true, showDeleteConfirm: false, formValues: {} };

  let createModalOpen = false;

  tools.set(`agented_${domain}_get_list_state`, {
    execute: vi.fn(async () => ({
      content: [{ type: 'text', text: JSON.stringify(listState) }],
    })),
  });

  tools.set(`agented_${domain}_get_modal_state`, {
    execute: vi.fn(async () => ({
      content: [{ type: 'text', text: JSON.stringify(createModalOpen ? modalOpen : modalClosed) }],
    })),
  });

  tools.set(`agented_${domain}_trigger_create`, {
    execute: vi.fn(async () => {
      createModalOpen = true;
      return { content: [{ type: 'text', text: JSON.stringify({ success: true, action: 'create_modal_opened' }) }] };
    }),
  });

  tools.set(`agented_${domain}_trigger_delete`, {
    inputSchema: {
      type: 'object',
      properties: { id: { type: 'string' } },
      required: ['id'],
    },
    execute: vi.fn(async (args: Record<string, unknown>) => ({
      content: [{ type: 'text', text: JSON.stringify({ success: true, action: 'delete_confirm_opened', id: args.id }) }],
    })),
  });

  return { tools, resetState: () => { createModalOpen = false; } };
}

describe('crud-cycle', () => {
  for (const domain of DOMAINS) {
    it(`${domain}: list → read state → open create modal → verify modal open`, async () => {
      const { tools, resetState } = createDomainToolMap(domain);
      resetState();

      // Step 1: Read list state
      const listResult = await invokeTool(`agented_${domain}_get_list_state`, {}, tools);
      expect(listResult.success).toBe(true);
      const listData = JSON.parse((listResult.data as any).content[0].text);
      expect(listData.itemCount).toBeGreaterThanOrEqual(0);

      // Step 2: Verify modal is initially closed
      const modalBefore = await invokeTool(`agented_${domain}_get_modal_state`, {}, tools);
      expect(modalBefore.success).toBe(true);
      const beforeData = JSON.parse((modalBefore.data as any).content[0].text);
      expect(beforeData.showCreateModal).toBe(false);

      // Step 3: Trigger create modal
      const createResult = await invokeTool(`agented_${domain}_trigger_create`, {}, tools);
      expect(createResult.success).toBe(true);
      const createData = JSON.parse((createResult.data as any).content[0].text);
      expect(createData.action).toBe('create_modal_opened');

      // Step 4: Verify modal is now open
      const modalAfter = await invokeTool(`agented_${domain}_get_modal_state`, {}, tools);
      expect(modalAfter.success).toBe(true);
      const afterData = JSON.parse((modalAfter.data as any).content[0].text);
      expect(afterData.showCreateModal).toBe(true);
    });
  }

  it('state tool mapping is correct for all action patterns', () => {
    expect(getStateToolForAction('agented_teams_trigger_create')).toBe('agented_teams_get_modal_state');
    expect(getStateToolForAction('agented_teams_trigger_delete')).toBe('agented_teams_get_modal_state');
    expect(getStateToolForAction('agented_agents_perform_search')).toBe('agented_agents_get_list_state');
    expect(getStateToolForAction('agented_agents_perform_sort')).toBe('agented_agents_get_list_state');
    expect(getStateToolForAction('agented_settings_switch_tab')).toBe('agented_settings_get_state');
    expect(getStateToolForAction('agented_navigate_to')).toBe('agented_get_page_info');
  });

  it('generateRandomInputs produces valid args for string fields', () => {
    const schema = {
      type: 'object',
      properties: {
        query: { type: 'string' },
        id: { type: 'string' },
        count: { type: 'number' },
        enabled: { type: 'boolean' },
      },
      required: ['query', 'id'],
    };

    const args = generateRandomInputs(schema);
    expect(typeof args.query).toBe('string');
    expect(typeof args.id).toBe('string');
    // Optional fields should NOT be present
    expect(args.count).toBeUndefined();
    expect(args.enabled).toBeUndefined();
  });
});
