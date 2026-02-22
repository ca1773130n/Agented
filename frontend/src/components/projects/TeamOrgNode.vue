<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'

defineProps<{
  data: {
    label: string
    color: string
    memberCount: number
    teamId: string
    leaderName?: string
    tierCounts?: { leader: number; senior: number; member: number }
  }
}>()
</script>

<template>
  <div class="team-org-node" :style="{ borderColor: data.color }">
    <Handle type="target" :position="Position.Top" />
    <div class="node-color-bar" :style="{ backgroundColor: data.color }"></div>
    <div class="node-content">
      <div class="node-name">{{ data.label }}</div>
      <div class="node-meta">{{ data.memberCount }} member{{ data.memberCount !== 1 ? 's' : '' }}</div>
      <div v-if="data.leaderName" class="node-leader">Lead: {{ data.leaderName }}</div>
      <div v-if="data.tierCounts" class="node-tiers">
        <span class="tier-badge tier-leader">L:{{ data.tierCounts.leader }}</span>
        <span class="tier-badge tier-senior">S:{{ data.tierCounts.senior }}</span>
        <span class="tier-badge tier-member">M:{{ data.tierCounts.member }}</span>
      </div>
    </div>
    <Handle type="source" :position="Position.Bottom" />
  </div>
</template>

<style scoped>
.team-org-node {
  background: var(--bg-secondary, #12121a);
  border: 2px solid var(--border-subtle, rgba(255, 255, 255, 0.1));
  border-radius: 10px;
  min-width: 160px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
}

.team-org-node:hover {
  background: var(--bg-tertiary, #1a1a24);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

.node-color-bar {
  height: 4px;
  width: 100%;
}

.node-content {
  padding: 12px 16px;
}

.node-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #f0f0f5);
  margin-bottom: 4px;
}

.node-meta {
  font-size: 11px;
  color: var(--text-tertiary, #606070);
}

.node-leader {
  font-size: 10px;
  color: var(--text-secondary, #a0a0b0);
  margin-top: 4px;
}

.node-tiers {
  display: flex;
  gap: 4px;
  margin-top: 4px;
}

.tier-badge {
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  font-weight: 500;
}

.tier-leader {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.12);
}

.tier-senior {
  color: #a855f7;
  background: rgba(168, 85, 247, 0.12);
}

.tier-member {
  color: #a0a0b0;
  background: rgba(160, 160, 176, 0.1);
}
</style>
