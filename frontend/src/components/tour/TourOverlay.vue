<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import TourSpotlight from './TourSpotlight.vue'

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

defineEmits<{
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

onMounted(() => {
  if (props.active) findTarget()
})

onUnmounted(cleanup)
</script>

<template>
  <div v-if="active && step" class="tour-overlay">
    <!-- Spotlight — delegated to TourSpotlight component -->
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

    <!-- Bottom bar -->
    <div class="tour-bottom-bar">
      <div class="tour-bar-left">
        <span class="tour-step-counter">
          STEP {{ stepNumber }} OF {{ totalSteps }}
        </span>
        <span v-if="substepLabel" class="tour-substep-label">{{ substepLabel }}</span>
      </div>
      <p class="tour-step-message">{{ effectiveTarget?.message || step.message }}</p>
      <div class="tour-actions">
        <button v-if="step.skippable" class="tour-skip-btn" @click="$emit('skip')">
          Skip
        </button>
        <button class="tour-next-btn" @click="$emit('next')">
          Next
        </button>
      </div>
    </div>
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
  font-family: 'Geist', 'Inter', -apple-system, system-ui, sans-serif;
  font-size: 13px;
  color: var(--text-tertiary);
}

/* === Bottom bar === */
.tour-bottom-bar {
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
  color: var(--accent-cyan);
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
  transition: border-color 150ms, color 150ms;
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
  transition: background 150ms;
  font-family: inherit;
}

.tour-next-btn:hover {
  background: var(--tour-glow-color);
}
</style>
