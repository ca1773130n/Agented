<script setup lang="ts">
defineProps<{
  title?: string;
  noPadding?: boolean;
}>();
</script>

<template>
  <div class="default-layout" :class="{ 'no-padding': noPadding }">
    <slot />
  </div>
</template>

<style scoped>
.default-layout {
  width: 100%;
  min-height: 100%;
}

.default-layout.no-padding {
  padding: 0;
}
</style>
