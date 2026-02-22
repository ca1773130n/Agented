<script setup lang="ts">
defineProps<{
  teamName: string | null;
  members: Array<{ name: string; agentId: string; agentType: string }>;
  tasks: Array<{ id: string; subject: string; status: string; owner?: string }>;
}>();

function statusClass(status: string): string {
  switch (status) {
    case 'completed':
      return 'badge-completed';
    case 'in_progress':
      return 'badge-in-progress';
    default:
      return 'badge-pending';
  }
}
</script>

<template>
  <div class="team-monitor">
    <div class="monitor-header">
      <span v-if="teamName" class="team-name">Team: {{ teamName }}</span>
      <span v-else class="team-waiting">Waiting for team creation...</span>
    </div>

    <!-- Members section -->
    <div class="monitor-section">
      <div class="section-label">Members</div>
      <div v-if="members.length === 0" class="section-empty">No members yet</div>
      <div v-else class="member-list">
        <span
          v-for="member in members"
          :key="member.agentId"
          class="member-badge"
        >
          <span class="member-name">{{ member.name }}</span>
          <span class="member-type">{{ member.agentType }}</span>
        </span>
      </div>
    </div>

    <!-- Tasks section -->
    <div class="monitor-section">
      <div class="section-label">Tasks</div>
      <div v-if="tasks.length === 0" class="section-empty">No tasks yet</div>
      <div v-else class="task-list">
        <div
          v-for="task in tasks"
          :key="task.id"
          class="task-row"
        >
          <span class="task-subject">{{ task.subject }}</span>
          <span class="task-owner" v-if="task.owner">{{ task.owner }}</span>
          <span class="task-status" :class="statusClass(task.status)">{{ task.status }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.team-monitor {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.monitor-header {
  margin-bottom: 10px;
}

.team-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.team-waiting {
  font-size: 13px;
  color: var(--text-muted);
  font-style: italic;
}

.monitor-section {
  margin-bottom: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-default);
}

.monitor-section:first-of-type {
  border-top: none;
  padding-top: 0;
}

.section-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.section-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0;
}

.member-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.member-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  padding: 3px 8px;
}

.member-name {
  font-size: 12px;
  font-family: 'Geist Mono', monospace;
  color: var(--text-primary);
}

.member-type {
  font-size: 10px;
  color: var(--text-muted);
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.task-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.task-subject {
  flex: 1;
  font-size: 12px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-owner {
  font-size: 11px;
  font-family: 'Geist Mono', monospace;
  color: var(--text-muted);
  flex-shrink: 0;
}

.task-status {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  padding: 2px 6px;
  border-radius: 3px;
  flex-shrink: 0;
}

.badge-completed {
  color: var(--accent-green);
  background: rgba(0, 200, 83, 0.1);
}

.badge-in-progress {
  color: var(--accent-cyan);
  background: rgba(0, 200, 255, 0.1);
}

.badge-pending {
  color: var(--text-muted);
  background: var(--bg-tertiary);
}
</style>
