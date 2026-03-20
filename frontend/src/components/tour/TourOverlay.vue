<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import type { TourStep } from '../../composables/useTour'

const props = defineProps<{
  active: boolean
  step: TourStep | null
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

function updateSpotlight() {
  if (!props.step?.target) {
    hasTarget.value = false
    return
  }
  const el = document.querySelector(props.step.target)
  if (!el) {
    hasTarget.value = false
    return
  }
  const rect = el.getBoundingClientRect()
  const padding = 12
  spotlightStyle.value = {
    top: `${rect.top - padding}px`,
    left: `${rect.left - padding}px`,
    width: `${rect.width + padding * 2}px`,
    height: `${rect.height + padding * 2}px`,
  }
  hasTarget.value = true

  // Scroll the target into view if needed
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function setupObserver() {
  teardownObserver()
  if (!props.step?.target) return
  const el = document.querySelector(props.step.target)
  if (!el) return
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      updateSpotlight()
    })
    resizeObserver.observe(el)
  }
}

function teardownObserver() {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
}

watch(
  () => props.step,
  async () => {
    if (props.active && props.step) {
      await nextTick()
      updateSpotlight()
      setupObserver()
      // Retry if target wasn't found yet (page may still be rendering after route change)
      if (!hasTarget.value) {
        for (let i = 0; i < 5; i++) {
          await new Promise(r => setTimeout(r, 300))
          updateSpotlight()
          if (hasTarget.value) {
            setupObserver()
            break
          }
        }
      }
    } else {
      hasTarget.value = false
      teardownObserver()
    }
  },
  { immediate: true },
)

watch(
  () => props.active,
  (val) => {
    if (val) {
      requestAnimationFrame(() => {
        barVisible.value = true
      })
    } else {
      barVisible.value = false
      teardownObserver()
    }
  },
  { immediate: true },
)

onMounted(() => {
  if (props.active && props.step) {
    updateSpotlight()
    setupObserver()
  }
})

onUnmounted(() => {
  teardownObserver()
})
</script>

<template>
  <div v-if="active && step" class="tour-overlay">
    <!-- Dim overlay (shown when no target found) -->
    <div v-if="!hasTarget" class="tour-dim" />

    <!-- Spotlight on target element (its box-shadow IS the dim layer) -->
    <div v-if="hasTarget" class="tour-spotlight" :style="spotlightStyle" />

    <!-- Bottom bar -->
    <div class="tour-bottom-bar" :class="{ 'tour-bottom-bar--visible': barVisible }">
      <div class="tour-bottom-bar__left">
        <span class="tour-step-tag">STEP {{ stepNumber }} OF {{ totalSteps }}</span>
        <span class="tour-step-message">{{ step.message }}</span>
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
        <button v-if="step.skippable" class="tour-skip-btn" @click="emit('skip')">Skip</button>
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

.tour-dim {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  pointer-events: none;
}

.tour-spotlight {
  position: fixed;
  border-radius: 10px;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.5), 0 0 24px 6px rgba(79, 70, 229, 0.35);
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
  background: linear-gradient(to top, rgba(9, 9, 11, 0.95) 60%, transparent);
  padding: 16px 24px;
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
  gap: 4px;
}

.tour-step-tag {
  color: #818cf8;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tour-step-message {
  color: #e0e0e0;
  font-size: 13px;
  line-height: 1.4;
}

.tour-bottom-bar__right {
  display: flex;
  flex-direction: row;
  gap: 12px;
  align-items: center;
}

.tour-progress-dots {
  display: flex;
  gap: 4px;
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
  background: #4f46e5;
}

.tour-dot--current {
  width: 16px;
  background: #4f46e5;
}

.tour-dot--remaining {
  width: 6px;
  background: transparent;
  border: 1px solid #333;
  box-sizing: border-box;
}

.tour-skip-btn {
  background: none;
  border: none;
  color: #666;
  font-size: 12px;
  cursor: pointer;
  padding: 6px 8px;
  font-family: inherit;
}

.tour-skip-btn:hover {
  color: #999;
}

.tour-next-btn {
  background: #4f46e5;
  color: white;
  border: none;
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 500;
}

.tour-next-btn:hover {
  background: #6366f1;
}
</style>
