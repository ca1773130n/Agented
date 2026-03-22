<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import TourSpotlight from './TourSpotlight.vue'
import TourTooltip from './TourTooltip.vue'
import TourProgressBar from './TourProgressBar.vue'

interface StepLike {
  target: string
  title: string
  message: string
  skippable: boolean
}

interface TargetLike {
  target: string
  message?: string
}

const props = defineProps<{
  active: boolean
  step: StepLike | null
  effectiveTarget: TargetLike | null
  substepLabel: string | null
  stepNumber: number
  totalSteps: number
}>()

const emit = defineEmits<{
  next: []
  skip: []
}>()

const targetEl = ref<HTMLElement | null>(null)
const targetRect = ref<DOMRect | null>(null)
let observer: MutationObserver | null = null
let resizeObserver: ResizeObserver | null = null
let tracking = false

function updateRect() {
  if (targetEl.value) {
    targetRect.value = targetEl.value.getBoundingClientRect()
  }
}

function startTracking() {
  if (tracking) return
  tracking = true
  window.addEventListener('scroll', updateRect, { capture: true, passive: true })
  window.addEventListener('resize', updateRect, { passive: true })
}

function stopTracking() {
  if (!tracking) return
  tracking = false
  window.removeEventListener('scroll', updateRect, true)
  window.removeEventListener('resize', updateRect)
}

function disconnectResizeObserver() {
  resizeObserver?.disconnect()
  resizeObserver = null
}

function observeTargetResize(el: HTMLElement) {
  disconnectResizeObserver()
  resizeObserver = new ResizeObserver(updateRect)
  resizeObserver.observe(el)
}

function findTarget() {
  const sel = props.effectiveTarget?.target || props.step?.target
  if (!sel) {
    targetEl.value = null
    targetRect.value = null
    return
  }
  const el = document.querySelector(sel) as HTMLElement | null
  targetEl.value = el
  if (el) {
    targetRect.value = el.getBoundingClientRect()
    observer?.disconnect()
    startTracking()
    observeTargetResize(el)
  } else {
    targetRect.value = null
  }
}

function cleanup() {
  observer?.disconnect()
  observer = null
  disconnectResizeObserver()
  stopTracking()
  targetEl.value = null
  targetRect.value = null
}

const SIGNIFICANT_STEP_TITLES = ['AI Backend Accounts']

function isSignificantStep(step: StepLike): boolean {
  return SIGNIFICANT_STEP_TITLES.includes(step.title)
}

watch(
  [() => props.active, () => props.step, () => props.effectiveTarget],
  () => {
    if (!props.active) {
      cleanup()
      return
    }
    findTarget()
    if (!targetEl.value) {
      observer?.disconnect()
      observer = new MutationObserver(findTarget)
      observer.observe(document.body, { childList: true, subtree: true })
    }
  },
  { immediate: true },
)

// Keyboard navigation — Enter=next, Escape=skip (when skippable)
function handleKeydown(e: KeyboardEvent) {
  if (!props.active || !props.step) return
  if (e.key === 'Enter') {
    e.preventDefault()
    emit('next')
  } else if (e.key === 'Escape') {
    if (props.step.skippable) {
      e.preventDefault()
      emit('skip')
    }
    // Non-skippable: do nothing (OB-33)
  }
}

onMounted(() => {
  if (props.active) findTarget()
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  cleanup()
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <!-- No dismiss on overlay click — OB-32: tour exits only via Skip/Next/complete -->
  <div v-if="active && step" class="tour-overlay" tabindex="-1" @click.stop>
    <!-- Spotlight highlight -->
    <TourSpotlight :target-rect="targetRect" :visible="!!targetRect" />

    <!-- Fullscreen dim when no target found yet -->
    <div v-if="!targetEl" class="tour-dim-fallback" />

    <!-- Loading spinner when target not yet in DOM -->
    <div v-if="!targetEl" class="tour-spinner">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinner-icon">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
      <span class="spinner-text">Loading...</span>
    </div>

    <!-- Tooltip anchored to spotlight target -->
    <TourTooltip
      :target-rect="targetRect"
      :title="step.title"
      :message="effectiveTarget?.message || step.message"
      :visible="!!targetRect"
    />

    <!-- Bottom progress bar -->
    <TourProgressBar
      :step-number="stepNumber"
      :total-steps="totalSteps"
      :substep-label="substepLabel"
      :message="effectiveTarget?.message || step.message"
      :skippable="step.skippable"
      :visible="true"
      :step-title="step.title"
      :skip-needs-confirm="step.skippable && isSignificantStep(step)"
      @next="$emit('next')"
      @skip="$emit('skip')"
    />
  </div>
</template>

<style scoped>
/* === Overlay === */
.tour-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-tour-overlay);
  pointer-events: none;
}

.tour-dim-fallback {
  position: fixed;
  inset: 0;
  background: var(--tour-overlay-dim);
}

/* === Spinner === */
.tour-spinner {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: var(--z-tour-tooltip);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  pointer-events: none;
}

.spinner-icon {
  width: 28px;
  height: 28px;
  color: var(--tour-glow-color);
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.spinner-text {
  font-size: 13px;
  color: var(--text-tertiary);
}
</style>
