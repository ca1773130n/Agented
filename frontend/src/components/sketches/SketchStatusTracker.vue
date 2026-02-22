<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  status: string;
}>();

const steps = ['draft', 'classified', 'routed', 'in_progress', 'completed'];

const stepLabels: Record<string, string> = {
  draft: 'Draft',
  classified: 'Classified',
  routed: 'Routed',
  in_progress: 'In Progress',
  completed: 'Completed',
};

const currentIndex = computed(() => {
  const idx = steps.indexOf(props.status);
  return idx >= 0 ? idx : 0;
});

const isArchived = computed(() => props.status === 'archived');

function stepClass(stepIdx: number): string {
  if (stepIdx < currentIndex.value) return 'step-completed';
  if (stepIdx === currentIndex.value) return 'step-current';
  return 'step-future';
}
</script>

<template>
  <div class="sketch-status-tracker">
    <h4 class="panel-title">Status</h4>
    <div class="pipeline">
      <div
        v-for="(step, idx) in steps"
        :key="step"
        class="pipeline-step"
        :class="stepClass(idx)"
      >
        <div class="step-connector" v-if="idx > 0"></div>
        <div class="step-circle">
          <svg v-if="idx < currentIndex" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" width="12" height="12">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          <span v-else class="step-dot"></span>
        </div>
        <span class="step-label">{{ stepLabels[step] }}</span>
      </div>
    </div>
    <div v-if="isArchived" class="archived-indicator">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
        <path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/>
      </svg>
      <span>Archived</span>
    </div>
  </div>
</template>

<style scoped>
.sketch-status-tracker {
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

.pipeline {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  position: relative;
}

.pipeline-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  position: relative;
}

.step-connector {
  position: absolute;
  top: 10px;
  right: 50%;
  width: 100%;
  height: 2px;
  background: var(--border-default);
  z-index: 0;
}

.step-completed .step-connector {
  background: var(--accent-primary);
}

.step-current .step-connector {
  background: var(--accent-primary);
}

.step-circle {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 1;
  background: var(--bg-primary);
  border: 2px solid var(--border-default);
  transition: all 0.2s ease;
}

.step-completed .step-circle {
  background: var(--accent-primary);
  border-color: var(--accent-primary);
  color: #fff;
}

.step-current .step-circle {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
}

.step-future .step-circle {
  opacity: 0.4;
}

.step-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--border-default);
}

.step-current .step-dot {
  background: var(--accent-primary);
}

.step-label {
  margin-top: 6px;
  font-size: 10px;
  color: var(--text-secondary);
  text-align: center;
  white-space: nowrap;
}

.step-current .step-label {
  color: var(--accent-primary);
  font-weight: 600;
}

.step-completed .step-label {
  color: var(--text-primary);
}

.step-future .step-label {
  opacity: 0.4;
}

.archived-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
