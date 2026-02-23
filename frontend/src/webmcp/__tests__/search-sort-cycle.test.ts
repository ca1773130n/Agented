/**
 * Search/sort cycle test: for each list page, exercises search and sort actions
 * then verifies the list state reflects the changes.
 */
import { describe, it, expect, vi } from 'vitest';
import { invokeTool } from '../test-harness/random-runner';

const SEARCHABLE_DOMAINS = ['agents', 'teams'];

function createSearchableToolMap(domain: string) {
  const tools = new Map<string, { execute: (a: Record<string, unknown>) => Promise<unknown>; inputSchema?: Record<string, unknown> }>();

  let currentSearch = '';
  let currentSortField = 'name';
  let currentSortOrder = 'asc';

  tools.set(`agented_${domain}_get_list_state`, {
    execute: vi.fn(async () => ({
      content: [{
        type: 'text',
        text: JSON.stringify({
          itemCount: currentSearch ? 1 : 5,
          isLoading: false,
          error: null,
          searchQuery: currentSearch,
          sortField: currentSortField,
          sortOrder: currentSortOrder,
        }),
      }],
    })),
  });

  tools.set(`agented_${domain}_perform_search`, {
    inputSchema: {
      type: 'object',
      properties: { query: { type: 'string' } },
      required: ['query'],
    },
    execute: vi.fn(async (args: Record<string, unknown>) => {
      currentSearch = (args.query as string) || '';
      return {
        content: [{ type: 'text', text: JSON.stringify({ success: true, searchQuery: currentSearch }) }],
      };
    }),
  });

  if (domain === 'agents') {
    tools.set(`agented_${domain}_perform_sort`, {
      inputSchema: {
        type: 'object',
        properties: {
          field: { type: 'string' },
          order: { type: 'string' },
        },
        required: ['field', 'order'],
      },
      execute: vi.fn(async (args: Record<string, unknown>) => {
        currentSortField = (args.field as string) || 'name';
        currentSortOrder = (args.order as string) || 'asc';
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({ success: true, sortField: currentSortField, sortOrder: currentSortOrder }),
          }],
        };
      }),
    });
  }

  return tools;
}

describe('search-sort-cycle', () => {
  for (const domain of SEARCHABLE_DOMAINS) {
    it(`${domain}: search filters results and state reflects query`, async () => {
      const tools = createSearchableToolMap(domain);

      // Step 1: Read initial state
      const initial = await invokeTool(`agented_${domain}_get_list_state`, {}, tools);
      expect(initial.success).toBe(true);
      const initialData = JSON.parse((initial.data as any).content[0].text);
      expect(initialData.searchQuery).toBe('');
      expect(initialData.itemCount).toBe(5);

      // Step 2: Perform search
      const searchResult = await invokeTool(`agented_${domain}_perform_search`, { query: 'alpha' }, tools);
      expect(searchResult.success).toBe(true);
      const searchData = JSON.parse((searchResult.data as any).content[0].text);
      expect(searchData.searchQuery).toBe('alpha');

      // Step 3: Verify state reflects search
      const afterSearch = await invokeTool(`agented_${domain}_get_list_state`, {}, tools);
      const afterData = JSON.parse((afterSearch.data as any).content[0].text);
      expect(afterData.searchQuery).toBe('alpha');
      expect(afterData.itemCount).toBe(1); // Filtered

      // Step 4: Clear search
      await invokeTool(`agented_${domain}_perform_search`, { query: '' }, tools);
      const afterClear = await invokeTool(`agented_${domain}_get_list_state`, {}, tools);
      const clearData = JSON.parse((afterClear.data as any).content[0].text);
      expect(clearData.searchQuery).toBe('');
      expect(clearData.itemCount).toBe(5); // All items back
    });
  }

  it('agents: sort changes field and order in state', async () => {
    const tools = createSearchableToolMap('agents');

    // Initial state
    const initial = await invokeTool('agented_agents_get_list_state', {}, tools);
    const initialData = JSON.parse((initial.data as any).content[0].text);
    expect(initialData.sortField).toBe('name');
    expect(initialData.sortOrder).toBe('asc');

    // Sort by date desc
    const sortResult = await invokeTool('agented_agents_perform_sort', { field: 'created_at', order: 'desc' }, tools);
    expect(sortResult.success).toBe(true);

    // Verify
    const after = await invokeTool('agented_agents_get_list_state', {}, tools);
    const afterData = JSON.parse((after.data as any).content[0].text);
    expect(afterData.sortField).toBe('created_at');
    expect(afterData.sortOrder).toBe('desc');
  });

  it('search with empty string resets filter', async () => {
    const tools = createSearchableToolMap('teams');

    await invokeTool('agented_teams_perform_search', { query: 'test' }, tools);
    const filtered = await invokeTool('agented_teams_get_list_state', {}, tools);
    expect(JSON.parse((filtered.data as any).content[0].text).itemCount).toBe(1);

    await invokeTool('agented_teams_perform_search', { query: '' }, tools);
    const all = await invokeTool('agented_teams_get_list_state', {}, tools);
    expect(JSON.parse((all.data as any).content[0].text).itemCount).toBe(5);
  });
});
