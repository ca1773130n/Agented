<script setup lang="ts">
defineProps<{
  searchQuery: string;
  sortField: string;
  sortOrder: 'asc' | 'desc';
  sortOptions: Array<{ value: string; label: string }>;
  resultCount: number;
  totalCount: number;
  placeholder?: string;
}>();

const emit = defineEmits<{
  (e: 'update:searchQuery', value: string): void;
  (e: 'update:sortField', value: string): void;
  (e: 'update:sortOrder', value: 'asc' | 'desc'): void;
}>();

function toggleSortOrder(current: 'asc' | 'desc') {
  emit('update:sortOrder', current === 'asc' ? 'desc' : 'asc');
}
</script>

<template>
  <div class="list-search-sort">
    <div class="search-group">
      <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/>
        <path d="M21 21l-4.35-4.35"/>
      </svg>
      <input
        type="text"
        class="search-input"
        :value="searchQuery"
        :placeholder="placeholder ?? 'Search...'"
        @input="emit('update:searchQuery', ($event.target as HTMLInputElement).value)"
      />
      <button
        v-if="searchQuery"
        class="clear-btn"
        aria-label="Clear search"
        @click="emit('update:searchQuery', '')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6L6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>
    <div class="sort-group">
      <label class="sort-label">Sort:</label>
      <select
        class="sort-select"
        :value="sortField"
        @change="emit('update:sortField', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="opt in sortOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
      <button
        class="sort-order-btn"
        :aria-label="sortOrder === 'asc' ? 'Sort ascending' : 'Sort descending'"
        :title="sortOrder === 'asc' ? 'Ascending' : 'Descending'"
        @click="toggleSortOrder(sortOrder)"
      >
        <svg v-if="sortOrder === 'asc'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 19V5M5 12l7-7 7 7"/>
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M19 12l-7 7-7-7"/>
        </svg>
      </button>
    </div>
    <span v-if="searchQuery" class="result-count">
      Showing {{ resultCount }} of {{ totalCount }}
    </span>
  </div>
</template>

<style scoped>
.list-search-sort {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.search-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 180px;
  position: relative;
}

.search-icon {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  background: transparent;
  border: none;
  font-size: 14px;
  color: var(--text-primary);
  outline: none;
  min-width: 100px;
}

.search-input::placeholder {
  color: var(--text-tertiary);
}

.clear-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-tertiary);
  border-radius: 4px;
  transition: color 0.15s;
}

.clear-btn:hover {
  color: var(--text-primary);
}

.clear-btn svg {
  width: 14px;
  height: 14px;
}

.sort-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.sort-label {
  color: var(--text-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.sort-select {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}

.sort-order-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.sort-order-btn:hover {
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.sort-order-btn svg {
  width: 16px;
  height: 16px;
}

.result-count {
  color: var(--text-secondary);
  font-size: 13px;
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
