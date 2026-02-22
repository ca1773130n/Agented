import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, nextTick } from 'vue';
import { useDataPage, type UseDataPageOptions } from '../useDataPage';

interface TestItem {
  id: number;
  name: string;
  status: string;
}

const mockItems: TestItem[] = [
  { id: 1, name: 'Alpha', status: 'active' },
  { id: 2, name: 'Beta', status: 'draft' },
  { id: 3, name: 'Gamma', status: 'active' },
];

function createTestComponent(options: UseDataPageOptions<TestItem>) {
  return defineComponent({
    setup() {
      return useDataPage<TestItem>(options);
    },
    template: '<div />',
  });
}

function defaultOptions(overrides: Partial<UseDataPageOptions<TestItem>> = {}): UseDataPageOptions<TestItem> {
  return {
    loadFn: vi.fn().mockResolvedValue({ items: mockItems, total: 3 }),
    filterOptions: {
      searchFields: ['name', 'status'] as (keyof TestItem)[],
    },
    ...overrides,
  };
}

describe('useDataPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns isLoading as true initially', () => {
    const opts = defaultOptions({
      loadFn: vi.fn().mockReturnValue(new Promise(() => {})),
    });
    const wrapper = mount(createTestComponent(opts));
    expect(wrapper.vm.isLoading).toBe(true);
  });

  it('calls loadFn on mount when loadOnMount is default', async () => {
    const loadFn = vi.fn().mockResolvedValue({ items: mockItems, total: 3 });
    const opts = defaultOptions({ loadFn });
    mount(createTestComponent(opts));
    await flushPromises();
    expect(loadFn).toHaveBeenCalledTimes(1);
  });

  it('does not call loadFn on mount when loadOnMount is false', async () => {
    const loadFn = vi.fn().mockResolvedValue({ items: mockItems, total: 3 });
    const opts = defaultOptions({ loadFn, loadOnMount: false });
    mount(createTestComponent(opts));
    await flushPromises();
    expect(loadFn).not.toHaveBeenCalled();
  });

  it('sets items after successful load', async () => {
    const opts = defaultOptions();
    const wrapper = mount(createTestComponent(opts));
    await flushPromises();
    expect(wrapper.vm.items).toEqual(mockItems);
  });

  it('sets isLoading to false after load completes', async () => {
    const opts = defaultOptions();
    const wrapper = mount(createTestComponent(opts));
    await flushPromises();
    expect(wrapper.vm.isLoading).toBe(false);
  });

  it('sets loadError on failed load', async () => {
    const opts = defaultOptions({
      loadFn: vi.fn().mockRejectedValue(new Error('Network failure')),
    });
    const wrapper = mount(createTestComponent(opts));
    await flushPromises();
    expect(wrapper.vm.loadError).toBe('Network failure');
    expect(wrapper.vm.isLoading).toBe(false);
  });

  it('clears loadError on retry', async () => {
    const loadFn = vi
      .fn()
      .mockRejectedValueOnce(new Error('Network failure'))
      .mockResolvedValueOnce({ items: mockItems, total: 3 });
    const opts = defaultOptions({ loadFn });
    const wrapper = mount(createTestComponent(opts));
    await flushPromises();
    expect(wrapper.vm.loadError).toBe('Network failure');

    await wrapper.vm.load();
    await flushPromises();
    expect(wrapper.vm.loadError).toBeNull();
    expect(wrapper.vm.items).toEqual(mockItems);
  });

  it('returns useListFilter properties', async () => {
    const opts = defaultOptions();
    const wrapper = mount(createTestComponent(opts));
    await flushPromises();
    expect(wrapper.vm).toHaveProperty('searchQuery');
    expect(wrapper.vm).toHaveProperty('sortField');
    expect(wrapper.vm).toHaveProperty('sortOrder');
    expect(wrapper.vm).toHaveProperty('filteredAndSorted');
  });

  it('returns usePagination object with currentPage, pageSize, totalPages', async () => {
    const opts = defaultOptions();
    const wrapper = mount(createTestComponent(opts));
    await flushPromises();
    expect(wrapper.vm.pagination).toBeDefined();
    expect(wrapper.vm.pagination.currentPage).toBeDefined();
    expect(wrapper.vm.pagination.pageSize).toBeDefined();
    expect(wrapper.vm.pagination.totalPages).toBeDefined();
  });

  it('sets pagination.totalCount from loadFn result total', async () => {
    const opts = defaultOptions({
      loadFn: vi.fn().mockResolvedValue({ items: mockItems, total: 100 }),
    });
    const wrapper = mount(createTestComponent(opts));
    await flushPromises();
    expect(wrapper.vm.pagination.totalCount.value).toBe(100);
  });

  it('defaults pagination.totalCount to items.length when total omitted', async () => {
    const opts = defaultOptions({
      loadFn: vi.fn().mockResolvedValue({ items: mockItems }),
    });
    const wrapper = mount(createTestComponent(opts));
    await flushPromises();
    expect(wrapper.vm.pagination.totalCount.value).toBe(mockItems.length);
  });

  it('filteredAndSorted reflects search query filtering', async () => {
    const opts = defaultOptions();
    const wrapper = mount(createTestComponent(opts));
    await flushPromises();

    expect(wrapper.vm.filteredAndSorted).toHaveLength(3);

    wrapper.vm.searchQuery = 'Alpha';
    await nextTick();
    expect(wrapper.vm.filteredAndSorted).toHaveLength(1);
    expect(wrapper.vm.filteredAndSorted[0].name).toBe('Alpha');
  });

  it('handles non-Error throw in loadFn', async () => {
    const opts = defaultOptions({
      loadFn: vi.fn().mockRejectedValue('string error'),
    });
    const wrapper = mount(createTestComponent(opts));
    await flushPromises();
    expect(wrapper.vm.loadError).toBe('string error');
  });
});
