<script setup lang="ts">
defineProps<{
  stepNumber: number
  totalSteps: number
  substepLabel: string | null
  message: string
  skippable: boolean
  visible: boolean
}>()

defineEmits<{
  next: []
  skip: []
}>()
</script>

<template>
  <div v-if="visible" class="tour-progress-bar">
    <div class="tour-bar-left">
      <span class="tour-step-counter">
        STEP {{ stepNumber }} OF {{ totalSteps }}
      </span>
      <span v-if="substepLabel" class="tour-substep-label">{{ substepLabel }}</span>
    </div>
    <p class="tour-step-message">{{ message }}</p>
    <div class="tour-actions">
      <button v-if="skippable" class="tour-skip-btn" @click="$emit('skip')">
        Skip
      </button>
      <button class="tour-next-btn" @click="$emit('next')">
        Next
      </button>
    </div>
  </div>
</template>

<style scoped>
.tour-progress-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: var(--z-tour-controls);
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 24px;
  background: var(--bg-tertiary);
  border-top: 1px solid var(--border-default);
  box-shadow: 0 -4px 24px var(--tour-overlay-dim);
  pointer-events: auto;
  font-family: 'Geist', 'Inter', -apple-system, system-ui, sans-serif;
}

.tour-bar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.tour-step-counter {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  color: var(--tour-glow-color);
  white-space: nowrap;
}

.tour-substep-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
}

.tour-step-message {
  flex: 1;
  margin: 0;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.4;
}

.tour-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.tour-skip-btn {
  padding: 6px 14px;
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color var(--transition-fast), color var(--transition-fast);
  font-family: inherit;
}

.tour-skip-btn:hover {
  border-color: var(--border-strong);
  color: var(--text-primary);
}

.tour-next-btn {
  padding: 6px 16px;
  background: var(--accent-cyan);
  color: var(--text-on-accent);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: filter var(--transition-fast);
  font-family: inherit;
}

.tour-next-btn:hover {
  filter: brightness(1.15);
}
</style>
