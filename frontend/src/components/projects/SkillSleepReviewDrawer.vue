<script setup lang="ts">
/**
 * SkillSleepReviewDrawer — review-then-adopt slide-over for a Skill-Sleep run.
 *
 * The SAFETY CORE of the surface. Shows the judge scores (current vs candidate),
 * the disjoint-split outcome, the verdict reason, and the candidate body. The
 * footer Adopt button — the only action that writes to disk — is double-gated:
 *   - client: disabled unless `run.status === 'accepted' && !run.adopted_at && !isAdopting`
 *   - server: POST .../adopt refuses non-accepted / stale / foreign-project runs
 * Adopt failures (`adoptError`) are surfaced inline, never swallowed.
 *
 * Frame mirrors SkillCreatePreviewDrawer (Teleport + useFocusTrap + close hygiene).
 */
import { computed, ref, toRef } from 'vue';
import { useI18n } from 'vue-i18n';
import type { SkillSleepRun } from '../../services/api';
import { useFocusTrap } from '../../composables/useFocusTrap';
import MarkdownContent from '../base/MarkdownContent.vue';

const props = defineProps<{
  open: boolean;
  run: SkillSleepRun | null;
  isAdopting: boolean;
  adoptError?: string | null;
}>();

const emit = defineEmits<{ adopt: [runId: number]; close: [] }>();
const { t } = useI18n();

const drawerEl = ref<HTMLElement | null>(null);
useFocusTrap(drawerEl, toRef(props, 'open'));

/** The client-side adopt gate (server re-checks; this is honest affordance). */
const canAdopt = computed(
  () => !!props.run && props.run.status === 'accepted' && !props.run.adopted_at && !props.isAdopting,
);

function pct(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—';
  return `${(val * 100).toFixed(0)}%`;
}

function formatDelta(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—';
  const sign = val >= 0 ? '+' : '';
  return `${sign}${(val * 100).toFixed(0)}%`;
}

function deltaClass(val: number | null | undefined): string {
  if (val === null || val === undefined) return 'delta--neutral';
  if (val > 0) return 'delta--up';
  if (val < 0) return 'delta--down';
  return 'delta--neutral';
}

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) emit('close');
}
function onEscape(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close');
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="props.open && props.run"
      class="ss-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ss-review-title"
      tabindex="-1"
      @click="onBackdropClick"
      @keydown="onEscape"
    >
      <aside ref="drawerEl" class="ss-drawer" tabindex="-1" @click.stop>
        <header class="ss-header">
          <div>
            <h3 id="ss-review-title">{{ t('skillSleep.reviewTitle') }}</h3>
            <p class="ss-subtitle">{{ props.run.skill_name }}</p>
          </div>
          <button
            type="button"
            class="ss-close"
            :aria-label="t('skillSleep.cancel')"
            @click="emit('close')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div class="ss-body">
          <!-- (a) Judge scores -->
          <section class="ss-section">
            <h4>{{ t('skillSleep.judgeScores') }}</h4>
            <div class="ss-grid">
              <div class="ss-stat">
                <span class="ss-stat-label">{{ t('skillSleep.current') }}</span>
                <span class="ss-stat-value">{{ pct(props.run.current_score) }}</span>
              </div>
              <div class="ss-stat">
                <span class="ss-stat-label">{{ t('skillSleep.candidate') }}</span>
                <span class="ss-stat-value">{{ pct(props.run.candidate_score) }}</span>
              </div>
              <div class="ss-stat">
                <span class="ss-stat-label">{{ t('skillSleep.delta') }}</span>
                <span :class="['ss-stat-value', deltaClass(props.run.delta)]">
                  {{ formatDelta(props.run.delta) }}
                </span>
              </div>
            </div>
          </section>

          <!-- (b) Outcome (disjoint held-out split) -->
          <section class="ss-section">
            <h4>{{ t('skillSleep.outcome') }}</h4>
            <div class="ss-grid">
              <div class="ss-stat">
                <span class="ss-stat-label">{{ t('skillSleep.before') }}</span>
                <span class="ss-stat-value">{{ pct(props.run.outcome_before_score) }}</span>
              </div>
              <div class="ss-stat">
                <span class="ss-stat-label">{{ t('skillSleep.after') }}</span>
                <span class="ss-stat-value">{{ pct(props.run.outcome_after_score) }}</span>
              </div>
              <div class="ss-stat">
                <span class="ss-stat-label">{{ t('skillSleep.delta') }}</span>
                <span :class="['ss-stat-value', deltaClass(props.run.outcome_delta)]">
                  {{ formatDelta(props.run.outcome_delta) }}
                </span>
              </div>
            </div>
            <p v-if="props.run.outcome_question_count" class="ss-muted">
              {{ t('skillSleep.questions', { n: props.run.outcome_question_count }) }}
            </p>
          </section>

          <!-- (c) Reason -->
          <section v-if="props.run.reason" class="ss-section">
            <h4>{{ t('skillSleep.reasonLabel') }}</h4>
            <p class="ss-reason">{{ props.run.reason }}</p>
          </section>

          <!-- (d) Candidate body (no diff: current body unavailable — see plan) -->
          <section class="ss-section">
            <h4>{{ t('skillSleep.candidateBody') }}</h4>
            <p class="ss-muted">{{ t('skillSleep.currentBodyUnavailable') }}</p>
            <MarkdownContent
              v-if="props.run.candidate_body"
              :content="props.run.candidate_body"
              data-testid="ss-candidate-body"
            />
          </section>
        </div>

        <footer class="ss-footer">
          <p v-if="props.adoptError" class="ss-adopt-error" data-testid="ss-adopt-error">
            {{ t('skillSleep.adoptFailed') }}: {{ props.adoptError }}
          </p>
          <div class="ss-footer-actions">
            <button type="button" class="btn" @click="emit('close')">
              {{ t('skillSleep.cancel') }}
            </button>
            <button
              type="button"
              class="btn btn-primary"
              data-testid="ss-adopt"
              :disabled="!canAdopt"
              @click="props.run && emit('adopt', props.run.id)"
            >
              {{ props.isAdopting ? t('skillSleep.adopting') : t('skillSleep.adopt') }}
            </button>
          </div>
        </footer>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.ss-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: flex-end;
  z-index: 1000;
}

.ss-drawer {
  width: min(560px, 100%);
  height: 100%;
  background: var(--bg-panel, #16181d);
  border-left: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
  display: flex;
  flex-direction: column;
}

.ss-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
}

.ss-header h3 {
  margin: 0;
  font-size: 1.05rem;
}

.ss-subtitle {
  margin: 4px 0 0;
  font-size: 0.85rem;
  color: var(--text-muted, #999);
}

.ss-close {
  background: none;
  border: none;
  color: var(--text-muted, #999);
  cursor: pointer;
  width: 28px;
  height: 28px;
}

.ss-close svg {
  width: 20px;
  height: 20px;
}

.ss-body {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.ss-section h4 {
  margin: 0 0 8px;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted, #999);
}

.ss-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.ss-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--bg-card-inner, rgba(255, 255, 255, 0.04));
  border-radius: 8px;
  padding: 10px 14px;
}

.ss-stat-label {
  font-size: 0.72rem;
  color: var(--text-muted, #999);
  text-transform: uppercase;
}

.ss-stat-value {
  font-size: 1.15rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.delta--up {
  color: var(--accent-green, #4ade80);
}
.delta--down {
  color: var(--accent-crimson, #f87171);
}
.delta--neutral {
  color: var(--text-muted, #999);
}

.ss-muted {
  font-size: 0.8rem;
  color: var(--text-muted, #999);
  margin: 8px 0 0;
}

.ss-reason {
  font-size: 0.9rem;
  color: var(--text-primary, #eee);
  margin: 0;
}

.ss-footer {
  border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
  padding: 14px 20px;
}

.ss-footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.ss-adopt-error {
  color: var(--accent-crimson, #f87171);
  font-size: 0.85rem;
  margin: 0 0 10px;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
