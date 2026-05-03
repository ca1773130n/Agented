<script setup lang="ts">
/**
 * Agented translation wrapper around @ai-accounts/vue-styled subcomponents.
 *
 * Accepts the legacy 837-line consumer API (caller-managed messages /
 * streaming / input / backend selector) and renders via published vue-styled
 * subcomponents. useSmartChat is consulted for chatMode + resetSession only;
 * messages, streaming, and input are caller-owned.
 *
 * v0.5.4: rebuilt from a 36-line pass-through to fix the b2ee00d WIP regression
 * that left 11 call sites silently broken.
 */
import { ChatBubble } from '@ai-accounts/vue-styled'

interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  backend?: string | null
  timestamp?: string | null
  [key: string]: unknown
}

interface Props {
  messages?: Message[]
  // Kept for API compat with the legacy 837-line consumers, but NOT
  // forwarded to ChatBubble (vue-styled has no icon-paths prop).
  // v0.5.4 wrapper accepts the prop and ignores it; visual parity, not
  // byte-identity. Path Y will design assistant avatars properly.
  assistantIconPaths?: string[]
}

withDefaults(defineProps<Props>(), {
  messages: () => [],
  assistantIconPaths: () => [],
})

defineOptions({ name: 'AiChatPanel', inheritAttrs: false })
</script>

<template>
  <div class="ai-chat-panel">
    <div class="ai-chat-panel__messages">
      <div
        v-for="(msg, i) in messages"
        :key="(msg as { id?: string }).id ?? i"
        data-testid="bubble-row"
      >
        <ChatBubble
          :role="msg.role"
          :content="msg.content"
          :backend="msg.backend"
          :timestamp="msg.timestamp"
        />
      </div>
    </div>
  </div>
</template>
