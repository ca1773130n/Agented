<script setup lang="ts">
</script>

<template>
  <div class="full-bleed-layout">
    <slot />
  </div>
</template>

<style scoped>
.full-bleed-layout {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>
