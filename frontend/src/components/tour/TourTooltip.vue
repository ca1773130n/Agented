<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useFloating, offset, flip, shift, arrow, autoUpdate } from '@floating-ui/vue'
import { useFocusTrap } from '../../composables/useFocusTrap'

function getTransitionDuration(): number {
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue('--tour-transition-speed')
    .trim()
  // e.g. "200ms" -> 200, "0ms" -> 0
  return parseInt(raw, 10) || 0
}

const props = defineProps<{
  targetRect: DOMRect | null
  title: string
  message: string
  visible: boolean
  placement?: 'top' | 'bottom' | 'left' | 'right'
}>()

// Virtual Element Bridge — new object on every targetRect change so Floating UI reacts
const virtualReference = computed(() => {
  if (!props.targetRect) return undefined
  const r = props.targetRect
  return {
    getBoundingClientRect: () => ({
      x: r.x,
      y: r.y,
      top: r.top,
      left: r.left,
      right: r.right,
      bottom: r.bottom,
      width: r.width,
      height: r.height,
    }),
  }
})

const floating = ref<HTMLElement | null>(null)
const floatingArrow = ref<HTMLElement | null>(null)

const { floatingStyles, placement: actualPlacement, middlewareData } = useFloating(
  virtualReference,
  floating,
  {
    placement: computed(() => props.placement ?? 'bottom'),
    middleware: [offset(12), flip(), shift({ padding: 8 }), arrow({ element: floatingArrow })],
    whileElementsMounted: autoUpdate,
  },
)

// Two-phase transition: fade out → reposition → fade in
const isVisible = ref(false)
const isTransitioning = ref(false)

watch(
  () => props.visible,
  (newVal) => {
    if (newVal) {
      // Small delay to let Floating UI compute position before showing
      isTransitioning.value = true
      requestAnimationFrame(() => {
        isVisible.value = true
        isTransitioning.value = false
      })
    } else {
      isVisible.value = false
    }
  },
  { immediate: true },
)

// On targetRect change while visible, do a two-phase transition
watch(
  () => props.targetRect,
  (_newRect, oldRect) => {
    if (!props.visible || !oldRect || !_newRect) return
    // Check if position changed significantly (more than 5px)
    const dx = Math.abs(_newRect.x - oldRect.x)
    const dy = Math.abs(_newRect.y - oldRect.y)
    if (dx > 5 || dy > 5) {
      isTransitioning.value = true
      isVisible.value = false
      // After fade-out, Floating UI repositions, then fade-in
      setTimeout(() => {
        isVisible.value = true
        isTransitioning.value = false
      }, getTransitionDuration())
    }
  },
)

// Arrow side computation from placement
const arrowSide = computed(() => {
  const side = actualPlacement.value.split('-')[0]
  return {
    top: 'bottom',
    bottom: 'top',
    left: 'right',
    right: 'left',
  }[side] ?? 'top'
})

const arrowStyle = computed(() => {
  const arrowData = middlewareData.value.arrow
  const style: Record<string, string> = {}
  if (arrowData?.x != null) style.left = `${arrowData.x}px`
  if (arrowData?.y != null) style.top = `${arrowData.y}px`
  style[arrowSide.value] = '-4px'
  return style
})

// Focus trap — contain Tab within tooltip while visible
const isTrapActive = computed(() => props.visible && isVisible.value)
useFocusTrap(floating, isTrapActive)
</script>

<template>
  <div
    v-if="visible && targetRect"
    ref="floating"
    class="tour-tooltip"
    :class="{ 'tour-tooltip--visible': isVisible && !isTransitioning }"
    :style="floatingStyles"
    tabindex="-1"
  >
    <h4 class="tour-tooltip-title">{{ title }}</h4>
    <p class="tour-tooltip-message">{{ message }}</p>
    <div ref="floatingArrow" class="tour-tooltip-arrow" :style="arrowStyle" />
  </div>
</template>

<style scoped>
.tour-tooltip {
  position: absolute;
  z-index: var(--z-tour-tooltip);
  max-width: 320px;
  padding: 16px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: var(--tour-spotlight-radius);
  box-shadow: 0 8px 32px var(--tour-overlay-dim);
  pointer-events: auto;
  opacity: 0;
  transform: translateY(4px);
  transition:
    opacity var(--tour-transition-speed) ease,
    transform var(--tour-transition-speed) ease;
}

.tour-tooltip--visible {
  opacity: 1;
  transform: translateY(0);
}

.tour-tooltip-title {
  margin: 0 0 6px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}

.tour-tooltip-message {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.tour-tooltip-arrow {
  position: absolute;
  width: 8px;
  height: 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  transform: rotate(45deg);
}

@media (prefers-reduced-motion: reduce) {
  .tour-tooltip {
    transition: none;
  }
}
</style>
