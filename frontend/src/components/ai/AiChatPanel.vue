<script setup lang="ts">
/**
 * Agented's AiChatPanel -- thin wrapper around @ai-accounts/vue-styled AiChatPanel.
 * Preserves the import path for existing views during migration.
 */
import { AiChatPanel as BaseAiChatPanel } from '@ai-accounts/vue-styled'

interface Props {
  density?: 'minimal' | 'detailed'
  defaultBackend?: string
  defaultModel?: string
  placeholder?: string
  welcomeTitle?: string
  welcomeSubtitle?: string
  readOnly?: boolean
  entityLabel?: string
  bannerTitle?: string
  bannerButtonLabel?: string
  showProcessGroups?: boolean
  showActions?: boolean
  configParser?: (content: string) => Record<string, unknown> | null
}

withDefaults(defineProps<Props>(), {
  density: 'detailed',
  placeholder: 'Type a message...',
})

const emit = defineEmits<{
  finalize: [config: Record<string, unknown> | null]
}>()
</script>

<template>
  <BaseAiChatPanel
    v-bind="$props"
    @finalize="emit('finalize', $event)"
  >
    <template v-for="(_, name) in $slots" #[name]="slotData">
      <slot :name="name" v-bind="slotData ?? {}" />
    </template>
  </BaseAiChatPanel>
</template>
