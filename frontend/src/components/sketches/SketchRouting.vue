<script setup lang="ts">
defineProps<{
  routing: Record<string, any> | null;
}>();

const emit = defineEmits<{
  (e: 'navigateTo', view: string, id?: string): void;
}>();

function handleTargetClick(routing: Record<string, any>) {
  if (routing.target_type === 'super_agent' && routing.target_id) {
    emit('navigateTo', 'super-agent-playground', routing.target_id);
  } else if (routing.target_type === 'team' && routing.target_id) {
    emit('navigateTo', 'team-dashboard', routing.target_id);
  }
}

function getTargetIcon(targetType: string): string {
  switch (targetType) {
    case 'super_agent':
      return 'M12 2a8 8 0 018 8v1a3 3 0 01-3 3h-1.5M2 10a8 8 0 018-8M9.5 14H8a3 3 0 01-3-3v-1';
    case 'team':
      return 'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 7a4 4 0 100-8 4 4 0 000 8M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75';
    default:
      return 'M12 2L2 7l10 5 10-5-10-5z';
  }
}
</script>

<template>
  <div class="sketch-routing">
    <h4 class="panel-title">Routing</h4>
    <div v-if="!routing" class="placeholder-text">Not yet routed</div>
    <div v-else-if="routing.target_type === 'none'" class="routing-none">
      <div class="none-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="20" height="20">
          <circle cx="12" cy="12" r="10"/>
          <line x1="15" y1="9" x2="9" y2="15"/>
          <line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
      </div>
      <span class="none-text">No matching target</span>
      <span v-if="routing.reason" class="suggestion-text">{{ routing.reason }}</span>
    </div>
    <div v-else class="routing-details">
      <div class="detail-row">
        <span class="detail-label">Target</span>
        <span class="target-type-badge">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
            <path :d="getTargetIcon(routing.target_type)"/>
          </svg>
          {{ routing.target_type === 'super_agent' ? 'SuperAgent' : routing.target_type }}
        </span>
      </div>
      <div class="detail-row">
        <span class="detail-label">ID</span>
        <a
          href="#"
          class="target-link"
          @click.prevent="handleTargetClick(routing)"
        >{{ routing.target_id }}</a>
      </div>
      <div v-if="routing.reason" class="detail-row">
        <span class="detail-label">Reason</span>
        <span class="reason-text">{{ routing.reason }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sketch-routing {
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-default);
}

.panel-title {
  margin: 0 0 12px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.placeholder-text {
  color: var(--text-secondary);
  font-size: 13px;
  font-style: italic;
}

.routing-none {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px;
}

.none-icon {
  color: var(--text-secondary);
  opacity: 0.6;
}

.none-text {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.suggestion-text {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
  font-style: italic;
}

.routing-details {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-label {
  font-size: 12px;
  color: var(--text-secondary);
  min-width: 60px;
  flex-shrink: 0;
}

.target-type-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  text-transform: capitalize;
}

.target-link {
  font-size: 12px;
  color: var(--accent-primary);
  text-decoration: none;
  font-family: monospace;
}

.target-link:hover {
  text-decoration: underline;
}

.reason-text {
  font-size: 12px;
  color: var(--text-primary);
  flex: 1;
}
</style>
