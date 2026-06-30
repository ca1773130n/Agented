<script setup lang="ts">
/**
 * PolicyAskCard (phase 23, 23-05).
 *
 * Renders an incoming `policy_ask` SSE event as an approval card and POSTs the
 * operator's decision to /admin/policies/decision via `policyApi.decide`. The
 * card blocks (Approve/Deny disabled, "awaiting" copy) until resolved, then
 * shows the resolution. Mirrors InteractiveQuestionCard's structure.
 */
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { policyApi } from '../../services/api';
import type { PolicyAskEvent, PolicyDecision } from '../../services/api';

const { t } = useI18n();

const props = defineProps<{
  event: PolicyAskEvent;
  sessionId: string;
}>();

const emit = defineEmits<{
  (e: 'resolved', decision: PolicyDecision): void;
}>();

const resolving = ref(false);
const resolved = ref<PolicyDecision | null>(null);
// 23 MINOR 8 — the backend reports whether a pending ASK was actually resolved
// (``ok``). ``ok:false`` means the wait was already resolved or timed out
// (fail-closed to deny) before our click landed, so we must NOT show a false
// success — surface the stale state instead.
const stale = ref(false);

async function decide(decision: PolicyDecision) {
  if (resolving.value || resolved.value || stale.value) return;
  resolving.value = true;
  try {
    const res = await policyApi.decide(props.sessionId, decision);
    if (res && res.ok) {
      resolved.value = decision;
      emit('resolved', decision);
    } else {
      // No pending ASK was resolved — already resolved/timed out elsewhere.
      stale.value = true;
    }
  } finally {
    resolving.value = false;
  }
}
</script>

<template>
  <div class="pac-card" :class="{ resolved: resolved !== null }">
    <div class="pac-header">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      </svg>
      <span>{{ t('policy.ask.title') }}</span>
      <span v-if="event.scope" class="pac-chip">{{ t('policy.ask.scope') }}: {{ event.scope }}</span>
    </div>

    <p class="pac-reason">
      <strong>{{ t('policy.ask.reason') }}:</strong> {{ event.reason }}
    </p>

    <div v-if="resolved !== null" class="pac-resolved">
      {{ t('policy.ask.resolved') }}:
      {{ resolved === 'approve' ? t('policy.ask.approve') : t('policy.ask.deny') }}
    </div>
    <div v-else-if="stale" class="pac-stale">
      {{ t('policy.ask.alreadyResolved') }}
    </div>
    <div v-else class="pac-actions">
      <span class="pac-awaiting">{{ t('policy.ask.awaiting') }}</span>
      <button
        type="button"
        class="pac-btn pac-btn-deny"
        :disabled="resolving"
        @click="decide('deny')"
      >
        {{ t('policy.ask.deny') }}
      </button>
      <button
        type="button"
        class="pac-btn pac-btn-approve"
        :disabled="resolving"
        @click="decide('approve')"
      >
        {{ t('policy.ask.approve') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.pac-card {
  border: 1px solid var(--color-warning, #d9a441);
  border-radius: 8px;
  padding: 14px 16px;
  background: var(--color-surface, #1c1c1e);
  color: var(--color-text, #e6e6e6);
  font-family: var(--font-family, 'Geist', system-ui, sans-serif);
}
.pac-card.resolved {
  border-color: var(--color-border, #333);
  opacity: 0.75;
}
.pac-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 8px;
}
.pac-header svg {
  width: 18px;
  height: 18px;
  color: var(--color-warning, #d9a441);
}
.pac-chip {
  margin-left: auto;
  font-size: 0.75rem;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-surface-2, #2a2a2d);
  color: var(--color-text-muted, #9a9a9a);
}
.pac-reason {
  margin: 0 0 12px;
  font-size: 0.9rem;
  line-height: 1.45;
}
.pac-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pac-awaiting {
  margin-right: auto;
  font-size: 0.8rem;
  color: var(--color-text-muted, #9a9a9a);
}
.pac-btn {
  border: 1px solid var(--color-border, #333);
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 0.85rem;
  cursor: pointer;
  background: transparent;
  color: inherit;
}
.pac-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.pac-btn-approve {
  background: var(--color-success, #2f855a);
  border-color: var(--color-success, #2f855a);
  color: #fff;
}
.pac-btn-deny {
  background: var(--color-danger, #c53030);
  border-color: var(--color-danger, #c53030);
  color: #fff;
}
.pac-resolved {
  font-size: 0.85rem;
  color: var(--color-text-muted, #9a9a9a);
}
.pac-stale {
  font-size: 0.85rem;
  color: var(--color-warning, #d9a441);
}
</style>
