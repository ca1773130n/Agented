<script setup lang="ts">
import AppBreadcrumb from './AppBreadcrumb.vue';

defineProps<{
  breadcrumbs: Array<{ label: string; action?: () => void }>;
  maxWidth?: string;
  fullHeight?: boolean;
}>();
</script>

<template>
  <div
    class="page-layout"
    :class="{ 'full-height': fullHeight }"
    :style="{ maxWidth: maxWidth || '1400px' }"
  >
    <AppBreadcrumb :items="breadcrumbs" />
    <slot />
  </div>
</template>

<style scoped>
.page-layout {
  margin: 0 auto;
}

.page-layout.full-height {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100vh;
  overflow: hidden;
}
</style>
