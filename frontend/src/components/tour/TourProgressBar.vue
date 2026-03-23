<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  stepNumber: number
  totalSteps: number
  substepLabel: string | null
  message: string
  skippable: boolean
  visible: boolean
  stepTitle: string
  skipNeedsConfirm: boolean
}>()

defineEmits<{
  next: []
  skip: []
}>()

const { t } = useI18n()
const confirmingSkip = ref(false)

function onSkipClick(emit: (evt: 'skip') => void) {
  if (props.skipNeedsConfirm) {
    confirmingSkip.value = true
  } else {
    emit('skip')
  }
}

function onConfirmSkip(emit: (evt: 'skip') => void) {
  confirmingSkip.value = false
  emit('skip')
}

watch([() => props.skippable, () => props.stepTitle], () => {
  confirmingSkip.value = false
})
</script>

<template>
  <div v-if="visible" class="tour-progress-bar">
    <div class="tour-bar-left">
      <span class="tour-step-title">{{ stepTitle }}</span>
      <div class="tour-bar-meta">
        <span class="tour-step-counter">
          {{ t('tour.stepOf', { current: stepNumber, total: totalSteps }) }}
        </span>
        <span v-if="substepLabel" class="tour-substep-label">{{ substepLabel }}</span>
      </div>
    </div>
    <div class="tour-bar-separator" />
    <p class="tour-step-message">{{ message }}</p>
    <div v-if="confirmingSkip" class="tour-skip-confirm">
      <span class="tour-skip-confirm-text">{{ t('tour.skipConfirmTitle') }} {{ t('tour.skipConfirmMessage') }}</span>
      <button class="tour-confirm-skip-btn" @click="onConfirmSkip($emit)">{{ t('tour.skipAnyway') }}</button>
      <button class="tour-cancel-skip-btn" @click="confirmingSkip = false">{{ t('tour.keepGoing') }}</button>
    </div>
    <div v-else class="tour-actions">
      <button v-if="skippable" class="tour-skip-btn" @click="onSkipClick($emit)">
        {{ t('common.skip') }}
      </button>
      <button class="tour-next-btn" @click="$emit('next')">
        {{ t('common.next') }}
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
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  flex-shrink: 0;
}

.tour-bar-separator {
  width: 1px;
  align-self: stretch;
  background: rgba(255, 255, 255, 0.12);
  flex-shrink: 0;
}

.tour-step-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  display: block;
  margin-bottom: 2px;
}

.tour-bar-meta {
  display: flex;
  align-items: center;
  gap: 8px;
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

.tour-skip-confirm {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.tour-skip-confirm-text {
  font-size: 12px;
  color: var(--text-secondary);
}

.tour-confirm-skip-btn {
  padding: 6px 14px;
  background: transparent;
  border: 1px solid var(--accent-crimson);
  color: var(--text-secondary);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color var(--transition-fast), color var(--transition-fast);
  font-family: inherit;
  white-space: nowrap;
}

.tour-confirm-skip-btn:hover {
  color: var(--text-primary);
}

.tour-cancel-skip-btn {
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
  white-space: nowrap;
}

.tour-cancel-skip-btn:hover {
  filter: brightness(1.15);
}
</style>
