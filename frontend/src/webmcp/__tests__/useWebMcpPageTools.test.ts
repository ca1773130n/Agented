/**
 * Unit tests for the useWebMcpPageTools factory composable.
 *
 * Validates that the factory registers the correct set of tools
 * (get_list_state, get_modal_state, trigger_create, trigger_delete)
 * and that execute handlers return valid ToolResponse shapes.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { defineComponent, h, ref, nextTick } from 'vue';
import { mount } from '@vue/test-utils';
import { useWebMcpPageTools } from '../useWebMcpPageTools';
import { getManifest, deregisterFromManifest } from '../tool-registry';

const mockUnregister = vi.fn();
const mockRegisterTool = vi.fn(() => ({ unregister: mockUnregister }));
const mockUnregisterTool = vi.fn();

beforeEach(() => {
  for (const entry of getManifest()) {
    deregisterFromManifest(entry.name);
  }
  mockRegisterTool.mockClear();
  mockUnregister.mockClear();
  mockUnregisterTool.mockClear();

  Object.defineProperty(navigator, 'modelContext', {
    value: {
      registerTool: mockRegisterTool,
      unregisterTool: mockUnregisterTool,
    },
    writable: true,
    configurable: true,
  });
});

function createListPageComponent(opts?: {
  includeModal?: boolean;
  includeActions?: boolean;
}) {
  const includeModal = opts?.includeModal ?? true;
  const includeActions = opts?.includeActions ?? true;

  return defineComponent({
    setup() {
      const items = ref([
        { id: 'item-1', name: 'Alpha' },
        { id: 'item-2', name: 'Beta' },
      ]);
      const isLoading = ref(false);
      const searchQuery = ref('');
      const showCreateModal = ref(false);
      const showDeleteConfirm = ref(false);
      const itemToDelete = ref<{ id: string; name: string } | null>(null);

      useWebMcpPageTools({
        page: 'TestListPage',
        domain: 'test_items',
        stateGetter: () => ({
          items: items.value,
          itemCount: items.value.length,
          isLoading: isLoading.value,
          error: null,
          searchQuery: searchQuery.value,
        }),
        ...(includeModal
          ? {
              modalGetter: () => ({
                showCreateModal: showCreateModal.value,
                showDeleteConfirm: showDeleteConfirm.value,
                formValues: {},
              }),
            }
          : {}),
        ...(includeActions
          ? {
              modalActions: {
                openCreate: () => {
                  showCreateModal.value = true;
                },
                openDelete: (id: string) => {
                  const found = items.value.find((i) => i.id === id);
                  if (found) {
                    itemToDelete.value = found;
                    showDeleteConfirm.value = true;
                  }
                },
              },
            }
          : {}),
        deps: [items, searchQuery],
      });

      return () => h('div', { 'data-testid': 'list-page' });
    },
  });
}

describe('useWebMcpPageTools factory', () => {
  it('registers 4 tools when all options provided', async () => {
    const Comp = createListPageComponent();
    const wrapper = mount(Comp);
    await nextTick();

    const manifest = getManifest();
    const names = manifest.map((e) => e.name).sort();
    expect(names).toEqual([
      'hive_test_items_get_list_state',
      'hive_test_items_get_modal_state',
      'hive_test_items_trigger_create',
      'hive_test_items_trigger_delete',
    ]);

    wrapper.unmount();
  });

  it('registers only get_list_state when no modal options', async () => {
    const Comp = createListPageComponent({ includeModal: false, includeActions: false });
    const wrapper = mount(Comp);
    await nextTick();

    const manifest = getManifest();
    expect(manifest).toHaveLength(1);
    expect(manifest[0].name).toBe('hive_test_items_get_list_state');

    wrapper.unmount();
  });

  it('get_list_state execute returns valid ToolResponse with correct data', async () => {
    const Comp = createListPageComponent();
    const wrapper = mount(Comp);
    await nextTick();

    const calls = mockRegisterTool.mock.calls as any[][];
    const listStateTool = calls.find((c) => c[0].name === 'hive_test_items_get_list_state');
    expect(listStateTool).toBeDefined();

    const result = await listStateTool![0].execute({});
    expect(result).toHaveProperty('content');
    expect(result.content[0].type).toBe('text');

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.itemCount).toBe(2);
    expect(parsed.isLoading).toBe(false);
    expect(parsed.error).toBeNull();
    expect(parsed.searchQuery).toBe('');

    wrapper.unmount();
  });

  it('get_modal_state returns modal visibility state', async () => {
    const Comp = createListPageComponent();
    const wrapper = mount(Comp);
    await nextTick();

    const calls = mockRegisterTool.mock.calls as any[][];
    const modalTool = calls.find((c) => c[0].name === 'hive_test_items_get_modal_state');
    expect(modalTool).toBeDefined();

    const result = await modalTool![0].execute({});
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.showCreateModal).toBe(false);
    expect(parsed.showDeleteConfirm).toBe(false);

    wrapper.unmount();
  });

  it('trigger_create returns success response', async () => {
    const Comp = createListPageComponent();
    const wrapper = mount(Comp);
    await nextTick();

    const calls = mockRegisterTool.mock.calls as any[][];
    const createTool = calls.find((c) => c[0].name === 'hive_test_items_trigger_create');
    expect(createTool).toBeDefined();

    const result = await createTool![0].execute({});
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(true);
    expect(parsed.action).toBe('create_modal_opened');

    wrapper.unmount();
  });

  it('trigger_delete requires id parameter', async () => {
    const Comp = createListPageComponent();
    const wrapper = mount(Comp);
    await nextTick();

    const calls = mockRegisterTool.mock.calls as any[][];
    const deleteTool = calls.find((c) => c[0].name === 'hive_test_items_trigger_delete');
    expect(deleteTool).toBeDefined();

    // Without id
    const result = await deleteTool![0].execute({});
    expect(result.isError).toBe(true);

    // With valid id
    const result2 = await deleteTool![0].execute({ id: 'item-1' });
    const parsed = JSON.parse(result2.content[0].text);
    expect(parsed.success).toBe(true);
    expect(parsed.id).toBe('item-1');

    wrapper.unmount();
  });

  it('deregisters all tools on unmount', async () => {
    const Comp = createListPageComponent();
    const wrapper = mount(Comp);
    await nextTick();
    expect(getManifest()).toHaveLength(4);

    wrapper.unmount();
    await nextTick();
    expect(getManifest()).toHaveLength(0);
  });

  it('all tools have correct page in manifest', async () => {
    const Comp = createListPageComponent();
    const wrapper = mount(Comp);
    await nextTick();

    const manifest = getManifest();
    for (const entry of manifest) {
      expect(entry.page).toBe('TestListPage');
    }

    wrapper.unmount();
  });

  it('trigger_delete has inputSchema with required id', async () => {
    const Comp = createListPageComponent();
    const wrapper = mount(Comp);
    await nextTick();

    const calls = mockRegisterTool.mock.calls as any[][];
    const deleteTool = calls.find((c) => c[0].name === 'hive_test_items_trigger_delete');
    expect(deleteTool![0].inputSchema).toEqual({
      type: 'object',
      properties: {
        id: { type: 'string', description: 'The entity ID to delete' },
      },
      required: ['id'],
    });

    wrapper.unmount();
  });
});
