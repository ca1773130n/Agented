<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useFormGuide, type FormField } from '../../composables/useFormGuide'

const props = defineProps<{
  active: boolean
  containerSelector: string
}>()

const emit = defineEmits<{
  'field-change': [field: { target: string; message: string } | null]
  'complete': []
}>()

const containerRef = ref<HTMLElement | null>(null)
const formGuide = useFormGuide(containerRef)

function emitCurrentField(): void {
  const field = formGuide.currentField.value
  if (field) {
    emit('field-change', { target: field.inputSelector, message: field.helpText })
  } else {
    emit('field-change', null)
  }
}

watch(
  () => props.active,
  async (isActive) => {
    if (isActive) {
      // Resolve container element
      await nextTick()
      containerRef.value = document.querySelector(props.containerSelector) as HTMLElement | null
      if (containerRef.value) {
        formGuide.activate()
        emitCurrentField()
      } else {
        emit('field-change', null)
      }
    } else {
      formGuide.deactivate()
      emit('field-change', null)
      containerRef.value = null
    }
  },
  { immediate: true },
)

watch(
  () => formGuide.currentField.value,
  (field: FormField | null) => {
    if (!props.active) return
    if (field) {
      emit('field-change', { target: field.inputSelector, message: field.helpText })
    } else {
      emit('field-change', null)
    }
  },
)

function nextField(): void {
  const advanced = formGuide.nextField()
  if (!advanced) {
    emit('complete')
  }
}

function prevField(): void {
  formGuide.prevField()
}

defineExpose({ nextField, prevField })
</script>

<template>
  <!-- Renderless component — visual output handled by TourOverlay -->
  <slot />
</template>
