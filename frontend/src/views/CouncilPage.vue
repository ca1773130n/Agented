<script setup lang="ts">
/**
 * Council (ai-accounts 0.4.5+) — convene a debating panel of your AI accounts to
 * decide a question. Streams the debate (positions → rebuttals over N rounds →
 * votes → the chair's decision) from the sidecar via SSE. See services/api/council.
 */
import { ref, computed, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { councilApi } from '../services/api/council';
import type { CouncilEvent } from '../services/api/council';

const { t } = useI18n();

const question = ref('');
const context = ref('');
const rounds = ref(1);
const options = ref<string[]>(['', '']);

const running = ref(false);
const error = ref<string | null>(null);
const events = ref<CouncilEvent[]>([]);
let controller: AbortController | null = null;

const canConvene = computed(
  () =>
    !running.value &&
    question.value.trim().length > 0 &&
    validOptions.value.length >= 2,
);
const validOptions = computed(() => options.value.map((o) => o.trim()).filter(Boolean));

// The panel is a fixed 5-lens roster (ai-accounts _ROLES); each member makes
// 1 position + `rounds` rebuttal calls, plus 1 chairman verdict. Surface the
// estimate so the operator sees the LLM cost before convening — it all lands on
// one account in the single-account case.
const PANEL_SIZE = 5;
const estCalls = computed(() => {
  const r = Number.isFinite(rounds.value) ? Math.max(0, Math.min(5, Math.trunc(rounds.value))) : 1;
  return PANEL_SIZE * (1 + r) + 1;
});

// Derived views over the streamed events.
const roster = computed(() => {
  const start = events.value.find((e) => e.kind === 'council_start');
  return (start?.payload?.members as Array<Record<string, unknown>>) ?? [];
});
// All lenses on one account → the debate is persona-diverse but single-model.
const singleAccount = computed(() => {
  const labels = new Set(roster.value.map((m) => m.account_label as string));
  return roster.value.length > 0 && labels.size === 1;
});
const debate = computed(() =>
  events.value.filter((e) => e.kind === 'position' || e.kind === 'rebuttal' || e.kind === 'member_error'),
);
const votes = computed(() => {
  const v = events.value.find((e) => e.kind === 'votes');
  return (v?.payload?.tally as Record<string, number>) ?? null;
});
const decision = computed(() => {
  const d = events.value.find((e) => e.kind === 'decision');
  return (d?.payload as CouncilDecision | undefined) ?? null;
});
const councilError = computed(() => events.value.find((e) => e.kind === 'council_error')?.error ?? null);

interface CouncilDecision {
  choice: number;
  choice_label: string;
  confidence?: number | null;
  rationale: string;
  dissent?: string;
  decided_by?: string;
}

function addOption() {
  if (options.value.length < 10) options.value.push('');
}
function removeOption(i: number) {
  if (options.value.length > 2) options.value.splice(i, 1);
}

async function convene() {
  if (!canConvene.value) return;
  running.value = true;
  error.value = null;
  events.value = [];
  controller = new AbortController();
  await councilApi.convene(
    {
      question: question.value.trim(),
      options: validOptions.value,
      context: context.value.trim() || undefined,
      rounds: rounds.value,
    },
    {
      onEvent: (e) => events.value.push(e),
      onError: (m) => { error.value = m; running.value = false; },
      onDone: () => { running.value = false; },
      signal: controller.signal,
    },
  );
}

function stop() {
  controller?.abort();
  running.value = false;
}

function memberLabel(e: CouncilEvent): string {
  return e.account_label || e.role || e.backend_kind || t('council.member');
}

onUnmounted(() => controller?.abort());
</script>

<template>
  <div class="council-page">
    <PageHeader :title="t('council.title')" :subtitle="t('council.subtitle')" />

    <form class="council-form" @submit.prevent="convene">
      <label class="council-label">{{ t('council.question') }}</label>
      <textarea
        v-model="question"
        class="council-textarea"
        rows="2"
        :placeholder="t('council.questionPlaceholder')"
        :disabled="running"
      />

      <label class="council-label">{{ t('council.options') }}</label>
      <div v-for="(_, i) in options" :key="i" class="council-option-row">
        <input
          v-model="options[i]"
          class="council-input"
          :placeholder="t('council.optionPlaceholder', { n: i + 1 })"
          :disabled="running"
        />
        <button
          type="button"
          class="council-opt-btn"
          :disabled="running || options.length <= 2"
          :title="t('council.removeOption')"
          @click="removeOption(i)"
        >−</button>
      </div>
      <button
        type="button"
        class="council-add-opt"
        :disabled="running || options.length >= 10"
        @click="addOption"
      >+ {{ t('council.addOption') }}</button>

      <div class="council-row">
        <div class="council-col">
          <label class="council-label">{{ t('council.rounds') }}</label>
          <input v-model.number="rounds" class="council-input council-input--sm" type="number" min="0" max="5" :disabled="running" />
        </div>
        <div class="council-col council-col--grow">
          <label class="council-label">{{ t('council.context') }}</label>
          <input v-model="context" class="council-input" :placeholder="t('council.contextPlaceholder')" :disabled="running" />
        </div>
      </div>

      <div class="council-actions">
        <button v-if="!running" class="council-convene" type="submit" :disabled="!canConvene">
          {{ t('council.convene') }}
        </button>
        <button v-else class="council-stop" type="button" @click="stop">{{ t('council.stop') }}</button>
        <span class="council-est" :title="t('council.estHint')">{{ t('council.estCalls', { n: estCalls }) }}</span>
      </div>
    </form>

    <div v-if="error" class="council-state council-state--error">{{ error }}</div>
    <div v-if="councilError" class="council-state council-state--error">{{ councilError }}</div>

    <!-- Roster -->
    <div v-if="roster.length" class="council-roster">
      <span class="council-roster__label">{{ t('council.panel') }}</span>
      <span v-for="(m, i) in roster" :key="i" class="council-member-pill">
        {{ m.account_label || m.role }} <em v-if="m.role">· {{ m.role }}</em>
      </span>
      <span v-if="running" class="council-spinner" />
    </div>
    <div v-if="singleAccount" class="council-note">{{ t('council.singleAccountNote') }}</div>

    <!-- Debate transcript -->
    <div v-if="debate.length" class="council-debate">
      <div
        v-for="(e, i) in debate"
        :key="i"
        class="council-turn"
        :class="{ 'council-turn--rebuttal': e.kind === 'rebuttal', 'council-turn--error': e.kind === 'member_error' }"
      >
        <div class="council-turn__head">
          <span class="council-turn__who">{{ memberLabel(e) }}</span>
          <span v-if="e.role" class="council-turn__role">{{ e.role }}</span>
          <span v-if="e.kind === 'rebuttal'" class="council-turn__round">{{ t('council.round', { n: e.round }) }}</span>
          <span v-if="e.option" class="council-turn__vote">{{ t('council.votedOption', { n: e.option }) }}</span>
        </div>
        <div v-if="e.text" class="council-turn__text">{{ e.text }}</div>
        <div v-if="e.error" class="council-turn__err">{{ e.error }}</div>
      </div>
    </div>

    <!-- Votes tally -->
    <div v-if="votes" class="council-votes">
      <span class="council-votes__label">{{ t('council.votes') }}</span>
      <span v-for="(count, label) in votes" :key="label" class="council-vote-pill">
        {{ label }} <b>{{ count }}</b>
      </span>
    </div>

    <!-- Decision -->
    <div v-if="decision" class="council-decision">
      <div class="council-decision__head">
        <span class="council-decision__badge">{{ t('council.decision') }}</span>
        <span class="council-decision__choice">{{ decision.choice_label }}</span>
        <span v-if="decision.confidence != null" class="council-decision__conf">
          {{ t('council.confidence', { p: Math.round(decision.confidence * 100) }) }}
        </span>
      </div>
      <p v-if="decision.rationale" class="council-decision__rationale">{{ decision.rationale }}</p>
      <p v-if="decision.dissent" class="council-decision__dissent">
        <strong>{{ t('council.dissent') }}:</strong> {{ decision.dissent }}
      </p>
      <span v-if="decision.decided_by" class="council-decision__by">{{ t('council.decidedBy', { by: decision.decided_by }) }}</span>
    </div>
  </div>
</template>

<style scoped>
.council-page { padding: 24px; max-width: 920px; }
.council-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: var(--bg-secondary, #12121a);
  margin: 16px 0 20px;
}
.council-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-secondary, #71717a);
  margin-top: 6px;
}
.council-textarea, .council-input {
  padding: 9px 12px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #e4e4e7);
  font-size: 14px;
  font-family: inherit;
  width: 100%;
  box-sizing: border-box;
}
.council-textarea:disabled, .council-input:disabled { opacity: 0.6; }
.council-input--sm { width: 72px; }
.council-option-row { display: flex; gap: 6px; align-items: center; }
.council-opt-btn {
  width: 30px; height: 30px; flex: none;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px; background: transparent;
  color: var(--text-secondary, #a1a1aa); cursor: pointer; font-size: 16px;
}
.council-opt-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.council-add-opt {
  align-self: flex-start;
  border: none; background: none; color: #a5b4fc;
  font-size: 13px; cursor: pointer; padding: 4px 0;
}
.council-add-opt:disabled { opacity: 0.5; cursor: not-allowed; }
.council-row { display: flex; gap: 12px; }
.council-col { display: flex; flex-direction: column; gap: 8px; }
.council-col--grow { flex: 1; }
.council-actions { margin-top: 12px; display: flex; align-items: center; gap: 12px; }
.council-est { font-size: 12px; color: var(--text-secondary, #71717a); }
.council-note {
  font-size: 12px;
  color: var(--text-secondary, #a1a1aa);
  margin-bottom: 16px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid rgba(234, 179, 8, 0.25);
  background: rgba(234, 179, 8, 0.08);
}
.council-convene, .council-stop {
  padding: 10px 22px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;
}
.council-convene {
  border: 1px solid rgba(79, 70, 229, 0.5);
  background: rgba(79, 70, 229, 0.18); color: #a5b4fc;
}
.council-convene:disabled { opacity: 0.5; cursor: not-allowed; }
.council-stop {
  border: 1px solid rgba(239, 68, 68, 0.5);
  background: rgba(239, 68, 68, 0.15); color: #f87171;
}
.council-state { padding: 16px; color: var(--text-secondary, #a1a1aa); font-size: 14px; }
.council-state--error { color: #ef4444; }
.council-roster { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 16px; }
.council-roster__label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--text-secondary, #71717a); }
.council-member-pill {
  font-size: 12px; padding: 3px 10px; border-radius: 100px;
  background: rgba(255, 255, 255, 0.06); color: var(--text-primary, #e4e4e7);
}
.council-member-pill em { color: var(--text-secondary, #a1a1aa); font-style: normal; }
.council-spinner {
  width: 13px; height: 13px;
  border: 2px solid rgba(165, 180, 252, 0.3); border-top-color: #a5b4fc;
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.council-debate { display: flex; flex-direction: column; gap: 10px; }
.council-turn {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-left-width: 3px; border-left-color: #6366f1;
  border-radius: 10px; padding: 12px 14px;
}
.council-turn--rebuttal { border-left-color: #eab308; }
.council-turn--error { border-left-color: #ef4444; }
.council-turn__head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.council-turn__who { font-size: 13px; font-weight: 600; color: var(--text-primary, #e4e4e7); }
.council-turn__role { font-size: 11px; color: var(--text-secondary, #71717a); text-transform: uppercase; letter-spacing: 0.3px; }
.council-turn__round { font-size: 11px; color: #eab308; }
.council-turn__vote { font-size: 11px; color: #4ade80; margin-left: auto; }
.council-turn__text { font-size: 13px; color: var(--text-secondary, #d4d4d8); margin-top: 6px; white-space: pre-wrap; }
.council-turn__err { font-size: 12px; color: #f87171; margin-top: 6px; }
.council-votes { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 18px 0; }
.council-votes__label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--text-secondary, #71717a); }
.council-vote-pill { font-size: 12px; padding: 3px 10px; border-radius: 100px; background: rgba(255, 255, 255, 0.06); color: var(--text-secondary, #a1a1aa); }
.council-vote-pill b { color: var(--text-primary, #e4e4e7); }
.council-decision {
  margin-top: 12px; padding: 18px;
  border: 1px solid rgba(34, 197, 94, 0.35);
  border-radius: 12px; background: rgba(34, 197, 94, 0.06);
}
.council-decision__head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.council-decision__badge {
  font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;
  color: #4ade80; padding: 3px 9px; border-radius: 100px; background: rgba(34, 197, 94, 0.15);
}
.council-decision__choice { font-size: 16px; font-weight: 700; color: var(--text-primary, #fff); }
.council-decision__conf { font-size: 12px; color: var(--text-secondary, #a1a1aa); }
.council-decision__rationale { font-size: 13px; color: var(--text-secondary, #d4d4d8); margin: 10px 0 0; }
.council-decision__dissent { font-size: 12px; color: var(--text-secondary, #a1a1aa); margin: 8px 0 0; }
.council-decision__by { font-size: 11px; color: var(--text-secondary, #71717a); display: block; margin-top: 8px; }
</style>
