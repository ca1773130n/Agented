<script setup lang="ts">
import { computed } from 'vue';
import type { EntityUsageEntry } from '../../services/api';
import { useTokenFormatting } from '../../composables/useTokenFormatting';

const { formatCurrency } = useTokenFormatting();

const props = defineProps<{
  entityData: EntityUsageEntry[];
  activeEntityTab: 'agent' | 'team' | 'trigger';
}>();

const emit = defineEmits<{
  (e: 'update:activeEntityTab', value: 'agent' | 'team' | 'trigger'): void;
}>();

const maxEntityCost = computed(() => {
  if (props.entityData.length === 0) return 1;
  return Math.max(...props.entityData.map(e => e.total_cost_usd), 0.01);
});
</script>

<template>
  <div class="section">
    <div class="section-header">
      <h2 class="section-title">Spend by Entity</h2>
      <div class="entity-tabs">
        <button
          class="tab-btn"
          :class="{ active: activeEntityTab === 'agent' }"
          @click="emit('update:activeEntityTab', 'agent')"
        >
          By Agent
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeEntityTab === 'team' }"
          @click="emit('update:activeEntityTab', 'team')"
        >
          By Team
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeEntityTab === 'trigger' }"
          @click="emit('update:activeEntityTab', 'trigger')"
        >
          By Trigger
        </button>
      </div>
    </div>

    <div v-if="entityData.length === 0" class="empty-state">
      No {{ activeEntityTab }} usage data for the selected period
    </div>

    <div v-else class="entity-list">
      <div class="entity-row" v-for="entity in entityData" :key="entity.entity_id">
        <div class="entity-info">
          <span class="entity-name">{{ entity.entity_name || entity.entity_id }}</span>
          <span class="entity-meta">
            {{ entity.execution_count }} execution{{ entity.execution_count !== 1 ? 's' : '' }}
            &middot;
            {{ entity.execution_count > 0 ? formatCurrency(entity.total_cost_usd / entity.execution_count) : '$0.00' }} avg
          </span>
        </div>
        <div class="entity-cost">
          <span class="cost-value">{{ formatCurrency(entity.total_cost_usd) }}</span>
          <div class="cost-bar-track">
            <div
              class="cost-bar-fill"
              :style="{ width: Math.max((entity.total_cost_usd / maxEntityCost) * 100, 2) + '%' }"
            ></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.section-title {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.entity-tabs {
  display: flex;
  gap: 4px;
}

.tab-btn {
  padding: 6px 14px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.tab-btn:hover {
  color: var(--text-primary);
  border-color: var(--border-default);
}

.tab-btn.active {
  color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
  border-color: transparent;
}

.entity-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.entity-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-radius: 8px;
  transition: background var(--transition-fast);
}

.entity-row:hover {
  background: var(--bg-tertiary);
}

.entity-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.entity-name {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
}

.entity-meta {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.entity-cost {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 200px;
}

.cost-value {
  font-family: var(--font-mono);
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--accent-violet);
  min-width: 70px;
  text-align: right;
}

.cost-bar-track {
  flex: 1;
  height: 6px;
  background: var(--bg-primary);
  border-radius: 3px;
  overflow: hidden;
  min-width: 80px;
}

.cost-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-violet), var(--accent-cyan));
  border-radius: 3px;
  transition: width 0.4s ease;
}
</style>
