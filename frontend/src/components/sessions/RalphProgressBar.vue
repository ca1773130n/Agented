<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  iteration: number;
  maxIterations: number;
  circuitBreakerTriggered: boolean;
  status: string;
}>();

const percent = computed(() => {
  if (props.maxIterations <= 0) return 0;
  return Math.min(100, Math.round((props.iteration / props.maxIterations) * 100));
});

const statusDotColor = computed(() => {
  if (props.circuitBreakerTriggered) return 'var(--accent-red)';
  switch (props.status) {
    case 'active':
      return 'var(--accent-green)';
    case 'paused':
      return 'var(--accent-yellow)';
    case 'completed':
      return 'var(--text-muted)';
    default:
      return 'var(--accent-red)';
  }
});
</script>

<template>
  <div class="ralph-progress">
    <div class="progress-header">
      <div class="progress-left">
        <span class="status-dot" :style="{ background: statusDotColor }" />
        <span class="progress-text">Iteration {{ iteration }} / {{ maxIterations }}</span>
      </div>
      <span
        v-if="circuitBreakerTriggered"
        class="circuit-badge"
      >CIRCUIT BREAK</span>
    </div>
    <div class="progress-track">
      <div
        class="progress-fill"
        :style="{ width: percent + '%' }"
      />
    </div>
  </div>
</template>

<style scoped>
.ralph-progress {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.progress-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.progress-text {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  font-family: 'Geist Mono', monospace;
}

.circuit-badge {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #fff;
  background: var(--accent-red);
  padding: 2px 8px;
  border-radius: 4px;
}

.progress-track {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent-cyan);
  border-radius: 2px;
  transition: width 0.3s ease;
}
</style>
