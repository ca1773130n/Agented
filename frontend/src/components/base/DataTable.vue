<script setup lang="ts">
export interface DataTableColumn {
  key: string;
  label: string;
  sortable?: boolean;
  width?: string;
  align?: 'left' | 'center' | 'right';
}

const props = withDefaults(
  defineProps<{
    columns: DataTableColumn[];
    items: any[];
    sortField?: string;
    sortOrder?: 'asc' | 'desc';
    rowClickable?: boolean;
  }>(),
  {
    sortField: '',
    sortOrder: 'asc',
    rowClickable: false,
  },
);

const emit = defineEmits<{
  (e: 'sort', field: string): void;
  (e: 'row-click', item: any): void;
}>();

function handleHeaderClick(col: DataTableColumn) {
  if (col.sortable) {
    emit('sort', col.key);
  }
}

function handleRowClick(item: any) {
  if (props.rowClickable) {
    emit('row-click', item);
  }
}
</script>

<template>
  <div class="ds-data-table-wrapper">
    <table class="ds-data-table">
      <thead>
        <tr>
          <th
            v-for="col in columns"
            :key="col.key"
            :class="{ 'ds-sortable-header': col.sortable }"
            :style="{ textAlign: col.align || 'left', width: col.width }"
            @click="handleHeaderClick(col)"
          >
            <slot :name="'header-' + col.key" :column="col">
              {{ col.label }}
            </slot>
            <span
              v-if="col.sortable && sortField === col.key"
              class="ds-sort-indicator"
            >{{ sortOrder === 'asc' ? '\u25B2' : '\u25BC' }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="items.length === 0">
          <td :colspan="columns.length">
            <slot name="empty" />
          </td>
        </tr>
        <template v-else>
          <tr
            v-for="(item, i) in items"
            :key="i"
            :class="{ 'ds-row-clickable': rowClickable }"
            @click="handleRowClick(item)"
          >
            <td
              v-for="col in columns"
              :key="col.key"
              :style="{ textAlign: col.align || 'left', width: col.width }"
            >
              <slot :name="'cell-' + col.key" :item="item" :value="item[col.key]" :column="col">
                <span>{{ item[col.key] }}</span>
              </slot>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.ds-data-table-wrapper {
  overflow-x: auto;
}

.ds-data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.ds-data-table th {
  text-align: left;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-muted);
  font-weight: 500;
  background: var(--bg-card);
  white-space: nowrap;
}

.ds-data-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-subtle, var(--border-color));
}

.ds-row-clickable:hover td {
  background: var(--bg-hover, rgba(255, 255, 255, 0.03));
  cursor: pointer;
}

.ds-sort-indicator {
  margin-left: 4px;
  opacity: 0.6;
}

.ds-sortable-header {
  cursor: pointer;
  user-select: none;
}
</style>
