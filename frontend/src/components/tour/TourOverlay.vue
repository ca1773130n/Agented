<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted, nextTick } from 'vue'
import type { TourStep, TourSubstep } from '../../composables/useTour'

const props = defineProps<{
  active: boolean
  step: TourStep | null
  effectiveTarget: (TourStep | TourSubstep) | null
  substepLabel: string | null
  stepNumber: number
  totalSteps: number
}>()

const emit = defineEmits<{
  next: []
  skip: []
}>()

const spotlightStyle = ref<Record<string, string>>({})
const hasTarget = ref(false)
const barVisible = ref(false)

let resizeObserver: ResizeObserver | null = null
let mutationObserver: MutationObserver | null = null
let targetEl: Element | null = null

const targetSelector = computed(() => props.effectiveTarget?.target ?? props.step?.target ?? '')
const displayMessage = computed(() => props.effectiveTarget?.message ?? props.step?.message ?? '')
const isSkippable = computed(() => {
  if (props.effectiveTarget && 'skippable' in props.effectiveTarget) {
    return props.effectiveTarget.skippable
  }
  return props.step?.skippable ?? false
})

function updateSpotlight() {
  const selector = targetSelector.value
  if (!selector) {
    hasTarget.value = false
    clearTargetHighlight()
    return
  }
  const el = document.querySelector(selector)
  if (!el) {
    hasTarget.value = false
    clearTargetHighlight()
    return
  }

  const rect = el.getBoundingClientRect()
  const padding = 16
  spotlightStyle.value = {
    top: `${rect.top - padding}px`,
    left: `${rect.left - padding}px`,
    width: `${rect.width + padding * 2}px`,
    height: `${rect.height + padding * 2}px`,
  }
  hasTarget.value = true
  applyTargetHighlight(el)
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function applyTargetHighlight(el: Element) {
  clearTargetHighlight()
  targetEl = el
  const htmlEl = el as HTMLElement
  htmlEl.style.position = htmlEl.style.position || 'relative'
  htmlEl.style.zIndex = '9998'
  htmlEl.style.outline = '3px solid #818cf8'
  htmlEl.style.outlineOffset = '6px'
  htmlEl.style.borderRadius = htmlEl.style.borderRadius || '8px'
  htmlEl.style.background = 'rgba(99, 102, 241, 0.06)'
  htmlEl.classList.add('tour-target-glow')
}

function clearTargetHighlight() {
  if (targetEl) {
    const htmlEl = targetEl as HTMLElement
    htmlEl.style.zIndex = ''
    htmlEl.style.outline = ''
    htmlEl.style.outlineOffset = ''
    htmlEl.style.background = ''
    htmlEl.classList.remove('tour-target-glow')
    targetEl = null
  }
}

function setupObserver() {
  teardownObserver()
  const selector = targetSelector.value
  if (!selector) return
  const el = document.querySelector(selector)
  if (!el) return
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => updateSpotlight())
    resizeObserver.observe(el)
  }
}

function teardownObserver() {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
}

function teardownMutationObserver() {
  if (mutationObserver) {
    mutationObserver.disconnect()
    mutationObserver = null
  }
}

function waitForTarget(selector: string) {
  teardownMutationObserver()
  mutationObserver = new MutationObserver(() => {
    const el = document.querySelector(selector)
    if (el) {
      teardownMutationObserver()
      updateSpotlight()
      setupObserver()
    }
  })
  mutationObserver.observe(document.body, {
    childList: true,
    subtree: true,
  })
}

// Watch effectiveTarget (changes on step AND substep changes)
watch(
  () => props.effectiveTarget,
  async () => {
    if (props.active && props.effectiveTarget) {
      hasTarget.value = false
      clearTargetHighlight()
      teardownMutationObserver()
      await nextTick()
      await new Promise(r => setTimeout(r, 100))
      updateSpotlight()
      setupObserver()
      if (!hasTarget.value && targetSelector.value) {
        waitForTarget(targetSelector.value)
      }
    } else {
      hasTarget.value = false
      clearTargetHighlight()
      teardownObserver()
      teardownMutationObserver()
    }
  },
  { immediate: true },
)

watch(
  () => props.active,
  (val) => {
    if (val) {
      requestAnimationFrame(() => { barVisible.value = true })
    } else {
      barVisible.value = false
      clearTargetHighlight()
      teardownObserver()
      teardownMutationObserver()
    }
  },
  { immediate: true },
)

onMounted(() => {
  if (!document.getElementById('tour-glow-style')) {
    const style = document.createElement('style')
    style.id = 'tour-glow-style'
    style.textContent = `
      @keyframes tour-pulse {
        0%, 100% {
          box-shadow: 0 0 20px 6px rgba(99,102,241,0.5), 0 0 60px 15px rgba(99,102,241,0.15);
          outline-color: #818cf8;
        }
        50% {
          box-shadow: 0 0 35px 12px rgba(99,102,241,0.7), 0 0 80px 25px rgba(99,102,241,0.2);
          outline-color: #a5b4fc;
        }
      }
      .tour-target-glow {
        animation: tour-pulse 1.5s ease-in-out infinite !important;
      }
      @keyframes tour-spin {
        to { transform: rotate(360deg); }
      }
    `
    document.head.appendChild(style)
  }
  if (props.active && props.effectiveTarget) {
    updateSpotlight()
    setupObserver()
  }
})

onUnmounted(() => {
  clearTargetHighlight()
  teardownObserver()
  teardownMutationObserver()
  const style = document.getElementById('tour-glow-style')
  if (style) style.remove()
})
</script>

<template>
  <div v-if="active && step" class="tour-overlay">
    <!-- Spotlight cutout (only when target found) -->
    <div v-if="hasTarget" class="tour-spotlight" :style="spotlightStyle" />

    <!-- Bottom bar -->
    <div class="tour-bottom-bar" :class="{ 'tour-bottom-bar--visible': barVisible }">
      <div class="tour-bottom-bar__left">
        <div class="tour-step-tag">
          STEP {{ stepNumber }} OF {{ totalSteps }}
          <span v-if="substepLabel" class="tour-substep-label"> — {{ substepLabel }}</span>
        </div>
        <div class="tour-step-message">
          <span v-if="!hasTarget" class="tour-spinner" />
          {{ displayMessage }}
        </div>
      </div>
      <div class="tour-bottom-bar__right">
        <div class="tour-progress-dots">
          <span
            v-for="i in totalSteps"
            :key="i"
            class="tour-dot"
            :class="{
              'tour-dot--completed': i < stepNumber,
              'tour-dot--current': i === stepNumber,
              'tour-dot--remaining': i > stepNumber,
            }"
          />
        </div>
        <button v-if="isSkippable" class="tour-skip-btn" @click="emit('skip')">Skip</button>
        <button class="tour-next-btn" @click="emit('next')">Next</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tour-overlay {
  position: fixed;
  inset: 0;
  z-index: 9998;
  pointer-events: none;
}

.tour-spotlight {
  position: fixed;
  border-radius: 12px;
  box-shadow: 0 0 0 9999px rgba(0, 0, 20, 0.75), 0 0 0 3px rgba(129, 140, 248, 0.8), 0 0 50px 15px rgba(99, 102, 241, 0.5);
  transition: all 400ms cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 9998;
  pointer-events: none;
}

.tour-bottom-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  pointer-events: auto;
  background: linear-gradient(to top, rgba(9, 9, 11, 0.98) 70%, rgba(9, 9, 11, 0.8) 85%, transparent);
  padding: 20px 32px;
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  align-items: center;
  transform: translateY(100%);
  transition: transform 400ms cubic-bezier(0.4, 0, 0.2, 1);
}

.tour-bottom-bar--visible {
  transform: translateY(0);
}

.tour-bottom-bar__left {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tour-step-tag {
  color: #818cf8;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.tour-substep-label {
  color: #a5b4fc;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 500;
}

.tour-step-message {
  color: #e4e4e7;
  font-size: 14px;
  line-height: 1.4;
  max-width: 600px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.tour-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(129, 140, 248, 0.3);
  border-top-color: #818cf8;
  border-radius: 50%;
  animation: tour-spin 0.8s linear infinite;
  flex-shrink: 0;
}

.tour-bottom-bar__right {
  display: flex;
  flex-direction: row;
  gap: 16px;
  align-items: center;
}

.tour-progress-dots {
  display: flex;
  gap: 5px;
  align-items: center;
}

.tour-dot {
  display: inline-block;
  height: 6px;
  border-radius: 3px;
  transition: width 300ms cubic-bezier(0.4, 0, 0.2, 1);
}

.tour-dot--completed {
  width: 6px;
  background: #6366f1;
}

.tour-dot--current {
  width: 20px;
  background: #818cf8;
}

.tour-dot--remaining {
  width: 6px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.15);
  box-sizing: border-box;
}

.tour-skip-btn {
  background: none;
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #a1a1aa;
  font-size: 13px;
  cursor: pointer;
  padding: 8px 16px;
  border-radius: 6px;
  font-family: inherit;
  transition: all 0.15s;
}

.tour-skip-btn:hover {
  color: #e4e4e7;
  border-color: rgba(255, 255, 255, 0.2);
}

.tour-next-btn {
  background: #6366f1;
  color: white;
  border: none;
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 500;
  transition: all 0.15s;
}

.tour-next-btn:hover {
  background: #818cf8;
}
</style>
