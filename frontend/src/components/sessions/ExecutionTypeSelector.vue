<script setup lang="ts">
const props = defineProps<{
  modelValue: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
}>();

function onChange(event: Event) {
  const target = event.target as HTMLSelectElement;
  emit('update:modelValue', target.value);
}
</script>

<template>
  <div class="execution-type-wrapper">
    <select
      class="execution-type-select"
      :value="modelValue"
      @change="onChange"
    >
      <option value="direct">Direct</option>
      <option value="ralph_loop">Ralph Loop</option>
      <option value="team_spawn">Team Spawn</option>
    </select>
    <p v-if="props.modelValue === 'ralph_loop'" class="prereq-notice">
      Requires ralph-wiggum plugin (claude plugin install ralph-wiggum@official --scope user)
    </p>
    <p v-else-if="props.modelValue === 'team_spawn'" class="prereq-notice">
      Requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 in environment
    </p>
  </div>
</template>

<style scoped>
.execution-type-wrapper {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.prereq-notice {
  margin: 4px 0 0 0;
  font-size: 11px;
  color: var(--text-muted);
  max-width: 260px;
  text-align: right;
  line-height: 1.3;
}

.execution-type-select {
  appearance: none;
  -webkit-appearance: none;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 6px 28px 6px 10px;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
}

.execution-type-select:hover {
  border-color: var(--border-subtle);
}

.execution-type-select:focus {
  border-color: var(--accent-cyan);
}

.execution-type-select option {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.execution-type-select option:disabled {
  color: var(--text-muted);
}
</style>
