<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue'
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
  retry: []
}>()

const targetEl = ref<HTMLElement | null>(null)
const targetRect = ref<DOMRect | null>(null)
let observer: MutationObserver | null = null
let resizeObserver: ResizeObserver | null = null
let tracking = false

// Loading timeout state (OB-40): 5s spinner-to-fallback
const loadingTimedOut = ref(false)
let routeLoadTimeout: ReturnType<typeof setTimeout> | null = null

// Element-not-found state (OB-41): 3s scoped observer fallback
const elementNotFoundTimeout = ref(false)
let elementFindTimeout: ReturnType<typeof setTimeout> | null = null

// Human-readable name for the element-not-found fallback
const currentTargetName = computed(() => {
  return props.step?.title ?? 'this element'
})

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

function clearTimers() {
  if (routeLoadTimeout !== null) {
    clearTimeout(routeLoadTimeout)
    routeLoadTimeout = null
  }
  if (elementFindTimeout !== null) {
    clearTimeout(elementFindTimeout)
    elementFindTimeout = null
  }
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
    clearTimers()
    loadingTimedOut.value = false
    elementNotFoundTimeout.value = false
    startTracking()
    observeTargetResize(el)
  } else {
    targetRect.value = null
  }
}

function handleRetry() {
  loadingTimedOut.value = false
  clearTimers()
  findTarget()
  emit('retry')
}

function handleElementRetry() {
  elementNotFoundTimeout.value = false
  clearTimers()
  findTarget()
  emit('retry')
}

function cleanup() {
  observer?.disconnect()
  observer = null
  disconnectResizeObserver()
  stopTracking()
  clearTimers()
  loadingTimedOut.value = false
  elementNotFoundTimeout.value = false
  targetEl.value = null
  targetRect.value = null
}

const SIGNIFICANT_STEP_TITLES = ['AI Backend Accounts']

function isSignificantStep(step: StepLike): boolean {
  return SIGNIFICANT_STEP_TITLES.includes(step.title)
}

function startObserverWithTimeouts() {
  if (targetEl.value) return // Already found

  observer?.disconnect()
  observer = new MutationObserver(findTarget)
  // OB-41: Scope observer to route root element, not document.body
  const scopeRoot = document.querySelector('#main-content') ?? document.body
  observer.observe(scopeRoot, { childList: true, subtree: true })

  // OB-40: 5s loading timeout — route may be slow to load
  if (routeLoadTimeout === null) {
    routeLoadTimeout = setTimeout(() => {
      routeLoadTimeout = null
      if (!targetEl.value) {
        loadingTimedOut.value = true
      }
    }, 5000)
  }

  // OB-41: 3s element-not-found timeout — route loaded but element missing
  if (elementFindTimeout === null) {
    elementFindTimeout = setTimeout(() => {
      elementFindTimeout = null
      if (!targetEl.value) {
        elementNotFoundTimeout.value = true
      }
    }, 3000)
  }
}

watch(
  [() => props.active, () => props.step, () => props.effectiveTarget],
  () => {
    if (!props.active) {
      cleanup()
      return
    }

    // Reset timeout states on step/target change
    loadingTimedOut.value = false
    elementNotFoundTimeout.value = false
    clearTimers()

    findTarget()
    if (!targetEl.value) {
      // Use nextTick + 100ms delay before starting observer (OB-41)
      nextTick(() => {
        setTimeout(() => {
          // Re-check — element may have appeared during the delay
          findTarget()
          if (!targetEl.value) {
            startObserverWithTimeouts()
          }
        }, 100)
      })
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

    <!-- Element-not-found fallback (OB-41) — takes precedence over loading timeout -->
    <div v-if="!targetEl && elementNotFoundTimeout" class="tour-element-fallback">
      <p>We couldn't find <strong>{{ currentTargetName }}</strong>.</p>
      <div class="fallback-actions">
        <button class="btn-fallback-skip" @click="$emit('skip')">Skip</button>
        <button class="btn-fallback-retry" @click="handleElementRetry">Retry</button>
      </div>
    </div>

    <!-- Loading timeout fallback (OB-40) — shows when route is slow but element timeout hasn't fired yet -->
    <div v-else-if="!targetEl && loadingTimedOut" class="tour-timeout-fallback">
      <p class="fallback-text">This page is taking longer than expected.</p>
      <div class="fallback-actions">
        <button class="btn-fallback-skip" @click="$emit('skip')">Skip</button>
        <button class="btn-fallback-retry" @click="handleRetry">Retry</button>
      </div>
    </div>

    <!-- Loading spinner when target not yet in DOM (no timeout yet) -->
    <div v-else-if="!targetEl" class="tour-spinner">
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

/* === Timeout Fallback (OB-40) === */
.tour-timeout-fallback,
.tour-element-fallback {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: var(--z-tour-tooltip);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  pointer-events: auto;
  text-align: center;
}

.tour-timeout-fallback .fallback-text,
.tour-element-fallback p {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.tour-element-fallback p strong {
  color: var(--text-primary);
}

.fallback-actions {
  display: flex;
  gap: 12px;
}

.btn-fallback-skip {
  padding: 6px 16px;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.btn-fallback-skip:hover {
  color: var(--text-secondary);
  border-color: var(--text-tertiary);
}

.btn-fallback-retry {
  padding: 6px 16px;
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
  background: transparent;
  color: var(--accent-cyan);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.btn-fallback-retry:hover {
  background: var(--accent-cyan);
  color: var(--bg-primary);
}
</style>
