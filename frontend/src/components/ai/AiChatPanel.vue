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
import { ref, computed, onMounted } from 'vue'
import { ChatBubble, ChatControls, FinalizationBanner } from '@ai-accounts/vue-styled'
import { useAiAccounts, useSmartScroll as _useSmartScroll } from '@ai-accounts/vue-headless'
import type { BackendDTO, BackendOption, ChatMode } from '@ai-accounts/ts-core'

// Loose Message shape — accepts both ConversationMessage (from
// Agented's services/api types) and the older inline shapes used by
// useConversation / useSketchChat. No index signature so consumer
// types don't need one.
interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  backend?: string | null
  timestamp?: string | null
}

interface Props {
  messages?: Message[]
  streamingContent?: string
  inputMessage?: string
  inputPlaceholder?: string
  isProcessing?: boolean
  showBackendSelector?: boolean
  selectedBackend?: string | null
  selectedAccountId?: string | null
  selectedModel?: string | null
  chatMode?: ChatMode
  // Finalization banner
  canFinalize?: boolean
  isFinalizing?: boolean
  bannerTitle?: string
  bannerButtonLabel?: string
  entityLabel?: string
  detectedEntityName?: string
  configParser?: (content: string) => Record<string, unknown> | null
  // Scroll + streaming hooks
  useSmartScroll?: boolean
  // Caller-supplied imperative hook. Legacy 837-line wrapper invoked it on
  // mount with whatever payload the caller's parser-init function expected
  // (typically an HTMLElement container). v0.5.4 wrapper preserves the
  // imperative contract but invokes with `undefined` — call sites that
  // need a typed payload should be migrated in path Y. Type signature is
  // intentionally `Function` so any caller-defined arity/type matches.
  // eslint-disable-next-line @typescript-eslint/no-unsafe-function-type
  initStreamingParser?: Function
  // Pass-through / display props that BaseAiChatPanel used to consume
  density?: 'minimal' | 'detailed'
  defaultBackend?: string
  defaultModel?: string
  placeholder?: string
  welcomeTitle?: string
  welcomeSubtitle?: string
  readOnly?: boolean
  showProcessGroups?: boolean
  showActions?: boolean
  // Kept for API compat with the legacy 837-line consumers, but NOT
  // forwarded to ChatBubble (vue-styled has no icon-paths prop).
  // v0.5.4 wrapper accepts the prop and ignores it; visual parity, not
  // byte-identity. Path Y will design assistant avatars properly.
  assistantIconPaths?: string[]
}

const props = withDefaults(defineProps<Props>(), {
  messages: () => [],
  streamingContent: '',
  inputMessage: '',
  inputPlaceholder: 'Type a message...',
  isProcessing: false,
  showBackendSelector: false,
  selectedBackend: null,
  selectedAccountId: null,
  selectedModel: null,
  chatMode: 'single',
  canFinalize: false,
  isFinalizing: false,
  bannerTitle: '',
  bannerButtonLabel: '',
  entityLabel: '',
  detectedEntityName: undefined,
  configParser: undefined,
  useSmartScroll: false,
  initStreamingParser: undefined,
  density: 'detailed',
  defaultBackend: undefined,
  defaultModel: undefined,
  placeholder: 'Type a message...',
  welcomeTitle: 'AI Chat',
  welcomeSubtitle: 'Send a message to get started',
  readOnly: false,
  showProcessGroups: undefined,
  showActions: undefined,
  assistantIconPaths: () => [],
})

const scroll = _useSmartScroll()

const emit = defineEmits<{
  'update:inputMessage': [value: string]
  // selectedBackend re-emitted as `string` (not nullable) for source-compat
  // with legacy 837-line consumers — useConversation.setBackend(s: string)
  // is non-nullable. ChatControls emits string | null when deselected;
  // the wrapper coerces null to '' at the boundary.
  'update:selectedBackend': [value: string]
  'update:selectedAccountId': [value: string | null]
  'update:selectedModel': [value: string | null]
  'update:chatMode': [value: ChatMode]
  send: []
  keydown: [event: KeyboardEvent]
  finalize: [config: Record<string, unknown> | null]
}>()

function onFinalize() {
  const lastAssistant = [...props.messages]
    .reverse()
    .find((m) => m.role === 'assistant')
  const config = props.configParser && lastAssistant
    ? props.configParser(lastAssistant.content)
    : null
  emit('finalize', config)
}

// Build the BackendOption[] list locally — useSmartChat does NOT expose
// backendOptions (codex review caught that hallucination). Mirrors the
// pattern in upstream BaseAiChatPanel.vue: listBackends → group by kind →
// fetch models lazily per kind.
const { client } = useAiAccounts()
const backends = ref<BackendDTO[]>([])
const modelsByKind = ref<Record<string, string[]>>({})
const internalChatMode = ref<ChatMode>(props.chatMode)

const backendOptions = computed<BackendOption[]>(() =>
  Array.from(new Set(backends.value.map((b) => b.kind))).map((kind) => {
    const forKind = backends.value.filter((b) => b.kind === kind)
    return {
      kind,
      displayName: kind,
      accounts: forKind.map((b) => ({ id: b.id, label: b.display_name || b.id })),
      models: modelsByKind.value[kind] ?? [],
    }
  }),
)

async function loadModelsFor(backend: BackendDTO) {
  if (modelsByKind.value[backend.kind]) return
  try {
    const { items } = await client.listModels(backend.id)
    modelsByKind.value = {
      ...modelsByKind.value,
      [backend.kind]: items.map((m) => m.id),
    }
  } catch {
    /* leave models empty; user can retry */
  }
}

onMounted(async () => {
  // The legacy 837-line wrapper handed callers a parser hook on mount.
  // Path Y will design the hook payload properly; for v0.5.4 we invoke
  // with no argument so source-compat callers can choose to ignore it.
  props.initStreamingParser?.()

  if (!props.showBackendSelector) return
  try {
    const { items } = await client.listBackends()
    backends.value = items
    await Promise.all(items.filter((b) => b.status === 'ready').map(loadModelsFor))
  } catch {
    backends.value = []
  }
})

defineOptions({ name: 'AiChatPanel', inheritAttrs: false })
</script>

<template>
  <div class="ai-chat-panel">
    <div class="ai-chat-panel__header">
      <slot name="header-extra" />
    </div>
    <div v-if="canFinalize" data-testid="finalize-banner">
      <FinalizationBanner
        :title="bannerTitle"
        :button-label="bannerButtonLabel"
        :entity-label="entityLabel"
        :entity-name="detectedEntityName"
        :is-finalizing="isFinalizing"
        @finalize="onFinalize"
      />
    </div>
    <div v-if="showBackendSelector" data-testid="backend-selector">
      <ChatControls
        :chat-mode="internalChatMode"
        :selected-backend="selectedBackend"
        :selected-account="selectedAccountId"
        :selected-model="selectedModel"
        :backends="backendOptions"
        @update:chatMode="(v: ChatMode) => { internalChatMode = v; emit('update:chatMode', v) }"
        @update:selectedBackend="(v: string | null) => emit('update:selectedBackend', v ?? '')"
        @update:selectedAccount="(v: string | null) => emit('update:selectedAccountId', v)"
        @update:selectedModel="(v: string | null) => emit('update:selectedModel', v)"
      />
    </div>
    <div
      class="ai-chat-panel__messages"
      :ref="useSmartScroll ? (el) => { scroll.containerRef.value = el as HTMLElement | null } : undefined"
    >
      <slot v-if="messages.length === 0" name="welcome" />
      <div
        v-for="(msg, i) in messages"
        :key="((msg as unknown as { id?: string }).id) ?? i"
        data-testid="bubble-row"
      >
        <ChatBubble
          :role="msg.role"
          :content="msg.content"
          :backend="msg.backend"
          :timestamp="msg.timestamp"
        />
      </div>
      <div v-if="streamingContent" data-testid="streaming-bubble">
        <ChatBubble
          role="assistant"
          :content="streamingContent"
          :streaming="true"
        />
      </div>
    </div>
    <!--
      Wrapper-owned input: vue-styled's ChatInput is uncontrolled (only
      placeholder/disabled/isStreaming props, single send(content) emit),
      so we render our own textarea to honour the legacy controlled
      :input-message + update:input-message + send + keydown contract.
    -->
    <div class="ai-chat-panel__input">
      <textarea
        data-testid="input"
        :value="inputMessage"
        :placeholder="inputPlaceholder"
        :disabled="isProcessing || readOnly"
        rows="3"
        @input="emit('update:inputMessage', ($event.target as HTMLTextAreaElement).value)"
        @keydown="(e: KeyboardEvent) => emit('keydown', e)"
      />
      <button
        data-testid="send"
        type="button"
        :disabled="isProcessing || readOnly"
        @click="emit('send')"
      >
        Send
      </button>
    </div>
  </div>
</template>
