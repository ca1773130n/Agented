<script setup lang="ts">
defineProps<{
  currentPage: number;
  totalPages: number;
  pageSize: number;
  pageSizeOptions: number[];
  rangeStart: number;
  rangeEnd: number;
  totalCount: number;
  isFirstPage: boolean;
  isLastPage: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:currentPage', value: number): void;
  (e: 'update:pageSize', value: number): void;
}>();

function onPageSizeChange(event: Event) {
  const value = parseInt((event.target as HTMLSelectElement).value, 10);
  emit('update:pageSize', value);
}
</script>

<template>
  <div v-if="totalCount > 0" class="pagination-bar">
    <span class="pagination-range">
      Showing {{ rangeStart }}-{{ rangeEnd }} of {{ totalCount }}
    </span>

    <div class="pagination-nav">
      <button
        class="pagination-btn"
        :disabled="isFirstPage"
        aria-label="Previous page"
        @click="emit('update:currentPage', currentPage - 1)"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M15 18l-6-6 6-6"/>
        </svg>
      </button>
      <span class="pagination-indicator">
        {{ currentPage }} of {{ totalPages }}
      </span>
      <button
        class="pagination-btn"
        :disabled="isLastPage"
        aria-label="Next page"
        @click="emit('update:currentPage', currentPage + 1)"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 18l6-6-6-6"/>
        </svg>
      </button>
    </div>

    <div class="pagination-size">
      <label class="pagination-size-label">Per page:</label>
      <select
        class="pagination-size-select"
        :value="pageSize"
        @change="onPageSizeChange"
      >
        <option v-for="opt in pageSizeOptions" :key="opt" :value="opt">{{ opt }}</option>
      </select>
    </div>
  </div>
</template>

<style scoped>
.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  margin-top: 24px;
  flex-wrap: wrap;
}

.pagination-range {
  color: var(--text-secondary);
  font-size: 13px;
  white-space: nowrap;
  flex-shrink: 0;
}

.pagination-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pagination-btn {
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

.pagination-btn:hover:not(:disabled) {
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.pagination-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.pagination-btn svg {
  width: 16px;
  height: 16px;
}

.pagination-indicator {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  min-width: 60px;
  text-align: center;
}

.pagination-size {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.pagination-size-label {
  color: var(--text-secondary);
  font-size: 13px;
  white-space: nowrap;
}

.pagination-size-select {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
}
</style>
