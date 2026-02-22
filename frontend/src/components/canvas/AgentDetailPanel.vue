<script setup lang="ts">
import { computed } from 'vue'
import type { TeamAgentAssignment } from '../../services/api'
import { teamApi } from '../../services/api'
import { useToast } from '../../composables/useToast'

const props = defineProps<{
  agentId: string
  memberId: number | null
  members: any[]
  assignments: TeamAgentAssignment[]
  teamId?: string
}>()

const emit = defineEmits<{
  close: []
  remove: [agentId: string]
  'tier-changed': [memberId: number, tier: string]
}>()

const showToast = useToast()

const member = computed(() => props.members.find(m => m.agent_id === props.agentId))

const agentAssignments = computed(() =>
  props.assignments.filter(a => a.agent_id === props.agentId)
)

function pillClass(type: string): string {
  switch (type) {
    case 'skill': return 'pill pill--skill'
    case 'command': return 'pill pill--command'
    case 'hook': return 'pill pill--hook'
    case 'rule': return 'pill pill--rule'
    default: return 'pill'
  }
}

async function onTierChange(event: Event) {
  const tier = (event.target as HTMLSelectElement).value
  if (!props.teamId || !props.memberId) return
  try {
    await teamApi.updateMember(props.teamId, props.memberId, { tier })
    emit('tier-changed', props.memberId, tier)
    showToast(`Tier updated to ${tier}`, 'success')
  } catch {
    showToast('Failed to update tier', 'error')
  }
}
</script>

<template>
  <div class="detail-panel">
    <div class="panel-header">
      <h3>Agent Details</h3>
      <button class="close-btn" @click="emit('close')" title="Close">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6L6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <div v-if="member" class="panel-body">
      <div class="info-row">
        <span class="info-label">Name</span>
        <span class="info-value">{{ member.name }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">Role</span>
        <span class="info-value">{{ member.role || 'member' }}</span>
      </div>
      <div class="info-row" v-if="member">
        <span class="info-label">Tier</span>
        <select
          class="tier-select"
          :value="member.tier || 'member'"
          @change="onTierChange"
        >
          <option value="leader">Leader</option>
          <option value="senior">Senior</option>
          <option value="member">Member</option>
        </select>
      </div>
      <div class="info-row" v-if="member.agent_id">
        <span class="info-label">Agent ID</span>
        <span class="info-value mono">{{ member.agent_id }}</span>
      </div>

      <div class="assignments-section">
        <span class="info-label">Assignments</span>
        <div v-if="agentAssignments.length === 0" class="no-assignments">
          No assignments
        </div>
        <div v-else class="assignment-list">
          <span
            v-for="a in agentAssignments"
            :key="a.id"
            :class="pillClass(a.entity_type)"
          >
            {{ a.entity_name || a.entity_id }}
          </span>
        </div>
      </div>

      <button class="remove-btn" @click="emit('remove', agentId)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
        </svg>
        Remove from Team
      </button>
    </div>

    <div v-else class="panel-body">
      <p class="no-member">Agent not found in team members</p>
    </div>
  </div>
</template>

<style scoped>
.detail-panel {
  width: 280px;
  background: var(--bg-secondary, #12121a);
  border-left: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
}

.panel-header h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #f0f0f5);
  margin: 0;
}

.close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-tertiary, #606070);
  transition: all 0.15s;
}

.close-btn:hover {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #f0f0f5);
}

.close-btn svg {
  width: 16px;
  height: 16px;
}

.panel-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary, #606070);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.info-value {
  font-size: 13px;
  color: var(--text-primary, #f0f0f5);
}

.info-value.mono {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--text-secondary, #a0a0b0);
}

.assignments-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.no-assignments {
  font-size: 12px;
  color: var(--text-tertiary, #606070);
  font-style: italic;
}

.assignment-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.pill {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 10px;
  display: inline-block;
  white-space: nowrap;
}

.pill--skill { background: rgba(34, 211, 238, 0.15); color: #22d3ee; }
.pill--command { background: rgba(74, 222, 128, 0.15); color: #4ade80; }
.pill--hook { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
.pill--rule { background: rgba(168, 85, 247, 0.15); color: #a855f7; }

.tier-select {
  width: 100%;
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #f0f0f5);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}

.tier-select:hover,
.tier-select:focus {
  border-color: var(--accent-cyan, #00d4ff);
}

.tier-select option {
  background: var(--bg-secondary, #12121a);
  color: var(--text-primary, #f0f0f5);
}

.remove-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  background: rgba(255, 51, 102, 0.1);
  color: var(--accent-crimson, #ff3366);
  transition: all 0.15s;
  margin-top: 8px;
}

.remove-btn:hover {
  background: rgba(255, 51, 102, 0.2);
}

.remove-btn svg {
  width: 14px;
  height: 14px;
}

.no-member {
  font-size: 12px;
  color: var(--text-tertiary, #606070);
  text-align: center;
  padding: 24px 0;
}
</style>
