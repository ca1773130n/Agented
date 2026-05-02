<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import TourSpotlight from './TourSpotlight.vue'
import TourTooltip from './TourTooltip.vue'
import TourProgressBar from './TourProgressBar.vue'
import { useTourTargetBus } from '../../composables/useTourTargetBus'

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

const props = withDefaults(defineProps<{
  active: boolean
  step: StepLike | null
  effectiveTarget: TargetLike | null
  substepLabel: string | null
  stepNumber: number
  totalSteps: number
  isModalOpen?: boolean
}>(), {
  isModalOpen: false,
})

const emit = defineEmits<{
  next: []
  skip: []
  retry: []
  dismiss: []
}>()

const { t } = useI18n()
const bus = useTourTargetBus()

const targetEl = ref<HTMLElement | null>(null)
const targetRect = ref<DOMRect | null>(null)
let unsubscribe: (() => void) | null = null
let resizeObserver: ResizeObserver | null = null
let scrollHandler: (() => void) | null = null

// OB-40: 5s "page is slow" fallback
const loadingTimedOut = ref(false)
let loadingTimer: ReturnType<typeof setTimeout> | null = null

// OB-41: 3s "element not found" fallback (precedence over OB-40)
const elementNotFoundTimeout = ref(false)
let elementTimer: ReturnType<typeof setTimeout> | null = null

const currentTargetName = computed(() => props.step?.title ?? 'this element')

const announcement = computed(() => {
  if (!props.active || !props.step) return ''
  const stepOf = t('tour.stepOf', { current: props.stepNumber, total: props.totalSteps })
  return `${stepOf}: ${props.step.title}. ${props.step.message}`
})

const currentSelector = computed(() =>
  props.effectiveTarget?.target || props.step?.target || null,
)

function isValidRect(rect: DOMRect): boolean {
  // Reject zero-dim rects and rects parked at origin during route transitions.
  if (rect.width === 0 || rect.height === 0) return false
  if (rect.top === 0 && rect.left === 0 && rect.bottom < 50) return false
  return true
}

function updateRect() {
  const el = targetEl.value
  if (!el || !el.isConnected) {
    targetRect.value = null
    return
  }
  const rect = el.getBoundingClientRect()
  targetRect.value = isValidRect(rect) ? rect : null
}

function attachToElement(el: HTMLElement) {
  targetEl.value = el
  updateRect()

  resizeObserver?.disconnect()
  resizeObserver = new ResizeObserver(updateRect)
  resizeObserver.observe(el)

  if (!scrollHandler) {
    scrollHandler = updateRect
    window.addEventListener('scroll', scrollHandler, { capture: true, passive: true })
    window.addEventListener('resize', scrollHandler, { passive: true })
  }

  // Re-read rect after layout settles — route transitions can shift elements.
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (targetEl.value === el) updateRect()
    })
  })
}

function detach() {
  targetEl.value = null
  targetRect.value = null
  resizeObserver?.disconnect()
  resizeObserver = null
  if (scrollHandler) {
    window.removeEventListener('scroll', scrollHandler, true)
    window.removeEventListener('resize', scrollHandler)
    scrollHandler = null
  }
}

function clearTimers() {
  if (loadingTimer !== null) { clearTimeout(loadingTimer); loadingTimer = null }
  if (elementTimer !== null) { clearTimeout(elementTimer); elementTimer = null }
}

function startTimers() {
  clearTimers()
  elementTimer = setTimeout(() => {
    elementTimer = null
    if (!targetEl.value) elementNotFoundTimeout.value = true
  }, 3000)
  loadingTimer = setTimeout(() => {
    loadingTimer = null
    if (!targetEl.value) loadingTimedOut.value = true
  }, 5000)
}

function unsubscribeFromBus() {
  unsubscribe?.()
  unsubscribe = null
}

function subscribeToSelector(sel: string | null) {
  unsubscribeFromBus()
  detach()
  clearTimers()
  loadingTimedOut.value = false
  elementNotFoundTimeout.value = false

  if (!sel || !props.active) return

  startTimers()
  unsubscribe = bus.subscribe(sel, (el) => {
    if (el) {
      attachToElement(el)
      clearTimers()
      loadingTimedOut.value = false
      elementNotFoundTimeout.value = false
    } else {
      detach()
      // Bus will re-emit when the element returns; restart fallback timers
      // so the user sees feedback if the element is gone for >3s.
      if (loadingTimer === null && elementTimer === null) startTimers()
    }
  })
}

function handleRetry() {
  loadingTimedOut.value = false
  elementNotFoundTimeout.value = false
  subscribeToSelector(currentSelector.value)
  emit('retry')
}

function handleElementRetry() {
  handleRetry()
}

// OB-31: skipping any of these requires confirmation. The criterion calls
// out "backend accounts, product/project creation" — the latter three
// titles match the step definitions in `src/constants/tourSteps.ts`.
const SIGNIFICANT_STEP_TITLES = [
  'AI Backend Accounts',
  'Create Your First Product',
  'Create Your First Project',
  'Assign Teams to Project',
]

function isSignificantStep(step: StepLike): boolean {
  return SIGNIFICANT_STEP_TITLES.includes(step.title)
}

// Step identity captures every prop combination that should retrigger the bus
// (selector + step title + substep label + message).
const stepIdentity = computed(() =>
  `${currentSelector.value}::${props.step?.title}::${props.substepLabel}::${props.step?.message}`,
)

watch(
  [() => props.active, stepIdentity],
  ([active]) => {
    if (active) {
      subscribeToSelector(currentSelector.value)
    } else {
      unsubscribeFromBus()
      detach()
      clearTimers()
      loadingTimedOut.value = false
      elementNotFoundTimeout.value = false
    }
  },
  { immediate: true },
)

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
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  unsubscribeFromBus()
  detach()
  clearTimers()
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <!-- No dismiss on overlay click — OB-32: tour exits only via Skip/Next/complete -->
  <div v-if="active && step" class="tour-overlay" tabindex="-1" @click.stop>
    <!-- OB-38: ARIA live announcements for screen readers -->
    <div
      aria-live="polite"
      aria-atomic="true"
      class="sr-only"
    >{{ announcement }}</div>

    <!-- Spotlight highlight (rect must have non-zero size — never anchor to 0,0) -->
    <TourSpotlight
      :target-rect="targetRect"
      :target-el="targetEl"
      :visible="!!targetRect && targetRect.width > 0 && targetRect.height > 0"
      :reduced="isModalOpen"
    />

    <!-- Fullscreen dim when no target found yet -->
    <div v-if="!targetEl" :class="['tour-dim-fallback', { 'modal-open': isModalOpen }]" />

    <!-- Element-not-found fallback (OB-41) — takes precedence over loading timeout -->
    <div v-if="!targetEl && elementNotFoundTimeout" class="tour-element-fallback">
      <p v-html="t('tour.elementNotFound', { element: `<strong>${currentTargetName}</strong>` })"></p>
      <div class="fallback-actions">
        <button class="btn-fallback-skip" @click="$emit('skip')">{{ t('common.skip') }}</button>
        <button class="btn-fallback-retry" @click="handleElementRetry">{{ t('common.retry') }}</button>
      </div>
    </div>

    <!-- Loading timeout fallback (OB-40) — shows when route is slow but element timeout hasn't fired yet -->
    <div v-else-if="!targetEl && loadingTimedOut" class="tour-timeout-fallback">
      <p class="fallback-text">{{ t('tour.pageSlow') }}</p>
      <div class="fallback-actions">
        <button class="btn-fallback-skip" @click="$emit('skip')">{{ t('common.skip') }}</button>
        <button class="btn-fallback-retry" @click="handleRetry">{{ t('common.retry') }}</button>
      </div>
    </div>

    <!-- Loading spinner when target not yet in DOM (no timeout yet) -->
    <div v-else-if="!targetEl" class="tour-spinner">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinner-icon">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
      <span class="spinner-text">{{ t('common.loading') }}</span>
    </div>

    <!-- Tooltip anchored to spotlight target — gate on rect validity so it
         never flashes at (0,0) when the host element is mid-transition. -->
    <TourTooltip
      :target-rect="targetRect"
      :title="step.title"
      :message="effectiveTarget?.message || step.message"
      :visible="!!targetRect && targetRect.width > 0 && targetRect.height > 0"
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
      @dismiss="$emit('dismiss')"
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
  transition: opacity 0.2s ease;
}

.tour-dim-fallback.modal-open {
  opacity: 0.3;
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

/* OB-38: Visually hidden but screen-reader accessible */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
