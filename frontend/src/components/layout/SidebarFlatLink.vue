<script setup lang="ts">
withDefaults(defineProps<{
  label: string;
  active?: boolean;
  collapsedDesktop?: boolean;
}>(), {
  active: false,
  collapsedDesktop: false,
});

const emit = defineEmits<{
  click: [];
}>();
</script>

<template>
  <button
    type="button"
    :class="{ active }"
    :aria-current="active ? 'page' : undefined"
    :title="collapsedDesktop ? label : undefined"
    @click="emit('click')"
  >
    <span class="nav-icon">
      <slot name="icon" />
    </span>
    <span class="nav-text">{{ label }}</span>
    <span class="nav-indicator"></span>
  </button>
</template>
