import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import DataTable from '../DataTable.vue';
import type { DataTableColumn } from '../DataTable.vue';

const columns: DataTableColumn[] = [
  { key: 'name', label: 'Name', sortable: true },
  { key: 'status', label: 'Status' },
  { key: 'date', label: 'Date', sortable: true, align: 'right' as const },
];

const items = [
  { name: 'Alpha', status: 'active', date: '2026-01-01' },
  { name: 'Beta', status: 'draft', date: '2026-02-01' },
];

function mountTable(overrides: Record<string, unknown> = {}) {
  return mount(DataTable, {
    props: { columns, items, ...overrides },
  });
}

describe('DataTable', () => {
  it('renders correct number of column headers', () => {
    const wrapper = mountTable();
    const ths = wrapper.findAll('th');
    expect(ths).toHaveLength(3);
  });

  it('renders correct number of rows', () => {
    const wrapper = mountTable();
    const rows = wrapper.findAll('tbody tr');
    expect(rows).toHaveLength(2);
  });

  it('renders column label text in headers', () => {
    const wrapper = mountTable();
    const headerTexts = wrapper.findAll('th').map((th) => th.text());
    expect(headerTexts[0]).toBe('Name');
    expect(headerTexts[1]).toBe('Status');
    expect(headerTexts[2]).toBe('Date');
  });

  it('renders item values in cells by default', () => {
    const wrapper = mountTable();
    const firstRowCells = wrapper.findAll('tbody tr:first-child td');
    expect(firstRowCells[0].text()).toBe('Alpha');
    expect(firstRowCells[1].text()).toBe('active');
    expect(firstRowCells[2].text()).toBe('2026-01-01');
  });

  it('renders custom cell content via cell-{key} scoped slot', () => {
    const wrapper = mount(DataTable, {
      props: { columns, items },
      slots: {
        'cell-status': `<template #cell-status="{ item, value }">
          <strong>{{ value.toUpperCase() }}</strong>
        </template>`,
      },
    });
    const statusCell = wrapper.find('tbody tr:first-child td:nth-child(2)');
    expect(statusCell.find('strong').text()).toBe('ACTIVE');
  });

  it('renders custom header content via header-{key} scoped slot', () => {
    const wrapper = mount(DataTable, {
      props: { columns, items },
      slots: {
        'header-name': `<template #header-name="{ column }">
          <em>{{ column.label }} (custom)</em>
        </template>`,
      },
    });
    const nameHeader = wrapper.find('th:first-child');
    expect(nameHeader.find('em').text()).toBe('Name (custom)');
  });

  it('emits sort event with field name when sortable header clicked', async () => {
    const wrapper = mountTable();
    await wrapper.findAll('th')[0].trigger('click');
    expect(wrapper.emitted('sort')).toBeTruthy();
    expect(wrapper.emitted('sort')![0]).toEqual(['name']);
  });

  it('does NOT emit sort when non-sortable header clicked', async () => {
    const wrapper = mountTable();
    await wrapper.findAll('th')[1].trigger('click'); // Status is not sortable
    expect(wrapper.emitted('sort')).toBeFalsy();
  });

  it('shows sort indicator on active sort column (asc)', () => {
    const wrapper = mountTable({ sortField: 'name', sortOrder: 'asc' });
    const indicator = wrapper.find('.ds-sort-indicator');
    expect(indicator.exists()).toBe(true);
    expect(indicator.text()).toBe('\u25B2');
  });

  it('shows sort indicator on active sort column (desc)', () => {
    const wrapper = mountTable({ sortField: 'name', sortOrder: 'desc' });
    const indicator = wrapper.find('.ds-sort-indicator');
    expect(indicator.exists()).toBe(true);
    expect(indicator.text()).toBe('\u25BC');
  });

  it('emits row-click event when row clicked and rowClickable is true', async () => {
    const wrapper = mountTable({ rowClickable: true });
    await wrapper.findAll('tbody tr')[0].trigger('click');
    expect(wrapper.emitted('row-click')).toBeTruthy();
    expect(wrapper.emitted('row-click')![0]).toEqual([items[0]]);
  });

  it('does NOT emit row-click when rowClickable is false', async () => {
    const wrapper = mountTable({ rowClickable: false });
    await wrapper.findAll('tbody tr')[0].trigger('click');
    expect(wrapper.emitted('row-click')).toBeFalsy();
  });

  it('applies ds-row-clickable class when rowClickable prop is true', () => {
    const wrapper = mountTable({ rowClickable: true });
    const rows = wrapper.findAll('tbody tr');
    expect(rows[0].classes()).toContain('ds-row-clickable');
  });

  it('does NOT apply ds-row-clickable class when rowClickable is false', () => {
    const wrapper = mountTable({ rowClickable: false });
    const rows = wrapper.findAll('tbody tr');
    expect(rows[0].classes()).not.toContain('ds-row-clickable');
  });

  it('renders empty slot when items array is empty', () => {
    const wrapper = mount(DataTable, {
      props: { columns, items: [] },
      slots: {
        empty: '<p class="no-data">No data available</p>',
      },
    });
    expect(wrapper.find('.no-data').exists()).toBe(true);
    expect(wrapper.find('.no-data').text()).toBe('No data available');
  });
});
