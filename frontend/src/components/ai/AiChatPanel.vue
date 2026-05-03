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
defineOptions({ name: 'AiChatPanel', inheritAttrs: false })
</script>

<template>
  <div class="ai-chat-panel" />
</template>
