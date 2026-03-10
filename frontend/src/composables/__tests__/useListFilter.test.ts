import { describe, it, expect, beforeEach } from 'vitest';
import { ref } from 'vue';
import { useListFilter } from '../useListFilter';

interface TestItem {
  name: string;
  status: string;
  priority: number;
}

const items = ref<TestItem[]>([
  { name: 'Alpha', status: 'active', priority: 3 },
  { name: 'Beta', status: 'draft', priority: 1 },
  { name: 'Gamma', status: 'active', priority: 2 },
]);

beforeEach(() => {
  items.value = [
    { name: 'Alpha', status: 'active', priority: 3 },
    { name: 'Beta', status: 'draft', priority: 1 },
    { name: 'Gamma', status: 'active', priority: 2 },
  ];
  sessionStorage.clear();
});

describe('useListFilter', () => {
  it('returns all items when no search query', () => {
    const { filteredAndSorted, totalCount } = useListFilter({
      items,
      searchFields: ['name', 'status'],
    });
    expect(filteredAndSorted.value).toHaveLength(3);
    expect(totalCount.value).toBe(3);
  });

  it('filters by search query across specified fields', () => {
    const { searchQuery, filteredAndSorted, hasActiveFilter } = useListFilter({
      items,
      searchFields: ['name', 'status'],
    });

    searchQuery.value = 'alpha';
    expect(filteredAndSorted.value).toHaveLength(1);
    expect(filteredAndSorted.value[0].name).toBe('Alpha');
    expect(hasActiveFilter.value).toBe(true);
  });

  it('filters by status field value', () => {
    const { searchQuery, filteredAndSorted } = useListFilter({
      items,
      searchFields: ['name', 'status'],
    });

    searchQuery.value = 'draft';
    expect(filteredAndSorted.value).toHaveLength(1);
    expect(filteredAndSorted.value[0].name).toBe('Beta');
  });

  it('sorts ascending by default', () => {
    const { filteredAndSorted } = useListFilter({
      items,
      searchFields: ['name'],
      defaultSort: { field: 'name', order: 'asc' },
    });

    expect(filteredAndSorted.value.map((i) => i.name)).toEqual(['Alpha', 'Beta', 'Gamma']);
  });

  it('sorts descending when configured', () => {
    const { filteredAndSorted } = useListFilter({
      items,
      searchFields: ['name'],
      defaultSort: { field: 'name', order: 'desc' },
    });

    expect(filteredAndSorted.value.map((i) => i.name)).toEqual(['Gamma', 'Beta', 'Alpha']);
  });

  it('sorts numerically with sortAccessors', () => {
    const { filteredAndSorted, sortField } = useListFilter({
      items,
      searchFields: ['name'],
      defaultSort: { field: 'priority', order: 'asc' },
      sortAccessors: {
        priority: (item) => item.priority,
      },
    });

    sortField.value = 'priority';
    expect(filteredAndSorted.value.map((i) => i.priority)).toEqual([1, 2, 3]);
  });

  it('reports resultCount matching filtered results', () => {
    const { searchQuery, resultCount, totalCount } = useListFilter({
      items,
      searchFields: ['name', 'status'],
    });

    searchQuery.value = 'active';
    expect(resultCount.value).toBe(2);
    expect(totalCount.value).toBe(3);
  });

  it('restores state from sessionStorage', () => {
    const key = 'test-filter';
    sessionStorage.setItem(key, JSON.stringify({ searchQuery: 'Beta', sortField: 'name', sortOrder: 'desc' }));

    const { searchQuery, sortField, sortOrder } = useListFilter({
      items,
      searchFields: ['name'],
      storageKey: key,
    });

    expect(searchQuery.value).toBe('Beta');
    expect(sortField.value).toBe('name');
    expect(sortOrder.value).toBe('desc');
  });
});
