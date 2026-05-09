<script setup lang="ts">
withDefaults(defineProps<{
  label: string;
  expanded: boolean;
  active?: boolean;
  collapsedDesktop?: boolean;
}>(), {
  active: false,
  collapsedDesktop: false,
});

const emit = defineEmits<{
  toggle: [];
}>();
</script>

<template>
  <button
    type="button"
    class="nav-group-toggle"
    :class="{ active }"
    :aria-expanded="expanded"
    :aria-current="active ? 'page' : undefined"
    :title="collapsedDesktop ? label : undefined"
    @click="emit('toggle')"
  >
    <span class="nav-icon">
      <slot name="icon" />
    </span>
    <span class="nav-text">{{ label }}</span>
    <svg
      class="chevron-icon"
      :class="{ expanded }"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
    >
      <polyline points="9,18 15,12 9,6"/>
    </svg>
    <span class="nav-indicator"></span>
  </button>
</template>
