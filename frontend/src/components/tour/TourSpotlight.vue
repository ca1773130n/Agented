<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  targetRect: DOMRect | null
  visible: boolean
  reduced?: boolean
}>(), {
  reduced: false,
})

// Suppress the CSS transition when the target rect jumps significantly
// (e.g., step change navigating to a different page) to avoid the spotlight
// sliding through the top-left corner on its way to the new position.
const suppressTransition = ref(false)

const spotlightStyle = computed(() => {
  if (!props.targetRect) return {}
  const r = props.targetRect
  const pad = parseInt(
    getComputedStyle(document.documentElement)
      .getPropertyValue('--tour-spotlight-padding')
      .trim() || '8',
    10,
  )
  const style: Record<string, string> = {
    top: `${r.top - pad}px`,
    left: `${r.left - pad}px`,
    width: `${r.width + pad * 2}px`,
    height: `${r.height + pad * 2}px`,
  }
  if (suppressTransition.value) {
    style.transition = 'none'
  }
  return style
})

watch(() => props.targetRect, (newRect, oldRect) => {
  if (!newRect || !oldRect) {
    // Target appeared or disappeared — skip transition to avoid sliding from/to (0,0)
    suppressTransition.value = true
    requestAnimationFrame(() => { suppressTransition.value = false })
    return
  }
  // Large position jump (>200px) = different element, not a scroll/resize — skip transition
  const dx = Math.abs(newRect.x - oldRect.x)
  const dy = Math.abs(newRect.y - oldRect.y)
  if (dx > 200 || dy > 200) {
    suppressTransition.value = true
    requestAnimationFrame(() => { suppressTransition.value = false })
  }
})
</script>

<template>
  <div
    v-if="targetRect"
    class="tour-spotlight"
    :class="{ 'tour-spotlight--visible': visible, 'tour-spotlight--reduced': reduced }"
    :style="spotlightStyle"
  >
    <div class="tour-spotlight-glow" />
  </div>
</template>

<style scoped>
.tour-spotlight {
  position: fixed;
  border-radius: var(--tour-spotlight-radius);
  z-index: var(--z-tour-spotlight);
  pointer-events: none;
  box-shadow: 0 0 0 9999px var(--tour-overlay-dim);
  transition:
    top var(--tour-transition-speed) ease,
    left var(--tour-transition-speed) ease,
    width var(--tour-transition-speed) ease,
    height var(--tour-transition-speed) ease;
  opacity: 0;
}

.tour-spotlight--visible {
  opacity: 1;
}

.tour-spotlight--reduced {
  opacity: 0.3;
}

.tour-spotlight-glow {
  position: absolute;
  inset: -4px;
  border-radius: calc(var(--tour-spotlight-radius) + 2px);
  border: 2px solid var(--tour-glow-color);
  animation: tour-glow 1.5s ease-in-out infinite;
}

/* Animate opacity on a fixed box-shadow to avoid paint thrashing (Research Pitfall 6) */
@keyframes tour-glow {
  0%,
  100% {
    box-shadow: 0 0 12px 3px var(--tour-glow-dim);
  }
  50% {
    box-shadow: 0 0 24px 6px var(--tour-glow-bright);
  }
}

@media (prefers-reduced-motion: reduce) {
  .tour-spotlight-glow {
    animation: none;
  }
  .tour-spotlight {
    transition: none;
  }
}
</style>
