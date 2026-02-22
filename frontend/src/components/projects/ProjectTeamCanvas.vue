<script setup lang="ts">
import OrgCanvas from '../canvas/OrgCanvas.vue'

defineProps<{
  projectId: string
  teams: { id: string; name: string; color: string; members?: any[] }[]
}>()

const emit = defineEmits<{
  'drill-down': [teamId: string]
}>()
</script>

<template>
  <OrgCanvas
    :project-id="projectId"
    :teams="teams"
    @drill-down="(id: string) => emit('drill-down', id)"
  />
</template>
