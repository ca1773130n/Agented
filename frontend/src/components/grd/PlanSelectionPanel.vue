<script setup lang="ts">
/** PlanSelectionPanel — GRD 0.4.5 deterministic plan-candidate selection.
 *  Per-phase: score PLAN-N.md candidates (dry-run preview), then promote the
 *  winner to PLAN.md. Generation of the candidates is LLM-driven (the planning
 *  session) and lives elsewhere; this panel is selection/scoring only. */
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdPlanningApi, ApiError } from '../../services/api';
import type { PlanCandidate, PlanSelectionResult } from '../../services/api';

const props = defineProps<{ projectId: string; phase: number }>();
const { t } = useI18n();

const expanded = ref(false);
const busy = ref(false);
const error = ref('');
const result = ref<PlanSelectionResult | null>(null);
const promotedTo = ref<string | null>(null);

async function toggle() {
  expanded.value = !expanded.value;
  if (expanded.value && !result.value) {
    // Load any prior mirrored selection (best-effort; 404 = none yet).
    try {
      const sel = await grdPlanningApi.getSelection(props.projectId, props.phase);
      if (sel?.candidates) {
        result.value = (sel.audit as PlanSelectionResult) ?? {
          phase: String(props.phase),
          candidates: sel.candidates,
          winner: null,
          promoted_to: sel.promoted_to,
        };
        promotedTo.value = sel.promoted_to;
      }
    } catch {
      /* no prior selection — leave empty */
    }
  }
}

async function run(dryRun: boolean) {
  error.value = '';
  busy.value = true;
  try {
    const res = await grdPlanningApi.selectCandidate(props.projectId, props.phase, {
      dry_run: dryRun,
    });
    result.value = res.data;
    promotedTo.value = res.data?.promoted_to ?? null;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('grdPlanSelection.failed');
  } finally {
    busy.value = false;
  }
}

function isWinner(c: PlanCandidate): boolean {
  return !!result.value?.winner && result.value.winner.relPath === c.relPath;
}
function pct(n: number | undefined): string {
  return typeof n === 'number' ? n.toFixed(2) : '—';
}
</script>

<template>
  <div class="plan-selection">
    <button class="ps-toggle" :data-testid="`plan-select-toggle-${phase}`" @click="toggle">
      {{ expanded ? '▾' : '▸' }} {{ t('grdPlanSelection.title') }}
    </button>
    <div v-if="expanded" class="ps-body">
      <p class="ps-help">{{ t('grdPlanSelection.help') }}</p>
      <div class="ps-actions">
        <button
          class="btn"
          :disabled="busy"
          :data-testid="`plan-select-score-${phase}`"
          @click="run(true)"
        >
          {{ busy ? t('grdPlanSelection.scoring') : t('grdPlanSelection.score') }}
        </button>
        <button
          class="btn btn-primary"
          :disabled="busy"
          :data-testid="`plan-select-promote-${phase}`"
          @click="run(false)"
        >
          {{ t('grdPlanSelection.promote') }}
        </button>
      </div>
      <p v-if="error" class="ps-error" :data-testid="`plan-select-error-${phase}`">{{ error }}</p>
      <p v-if="promotedTo" class="ps-promoted">{{ t('grdPlanSelection.promotedTo', { path: promotedTo }) }}</p>

      <ul v-if="result && result.candidates.length" class="ps-list">
        <li
          v-for="c in result.candidates"
          :key="c.relPath"
          class="ps-row"
          :class="{ winner: isWinner(c), 'hard-fail': c.hard_fail }"
        >
          <span class="ps-name">{{ c.relPath }}</span>
          <span v-if="isWinner(c)" class="ps-badge ps-badge-win">{{ t('grdPlanSelection.winner') }}</span>
          <span v-if="c.hard_fail" class="ps-badge ps-badge-fail">
            {{ t('grdPlanSelection.deadEnd', { slug: c.hard_fail.dead_end_slug }) }}
          </span>
          <span
            v-if="c.cluster && !c.cluster.is_representative"
            class="ps-badge ps-badge-merged"
          >{{ t('grdPlanSelection.mergedInto', { rep: c.cluster.merged_into }) }}</span>
          <span class="ps-score">{{ t('grdPlanSelection.scoreLabel', { score: pct(c.total_score) }) }}</span>
          <span v-if="c.base_breakdown" class="ps-axes">
            c {{ pct(c.base_breakdown.completeness) }} ·
            g {{ pct(c.base_breakdown.goal_alignment) }} ·
            h {{ pct(c.base_breakdown.hypothesis_quality) }} ·
            z {{ pct(c.base_breakdown.conciseness) }}
          </span>
        </li>
      </ul>
      <p v-else-if="result" class="ps-empty">{{ t('grdPlanSelection.noCandidates') }}</p>
    </div>
  </div>
</template>

<style scoped>
.plan-selection { margin-top: 8px; border-top: 1px solid var(--border-subtle, #2a2a36); padding-top: 6px; }
.ps-toggle { background: none; border: none; color: var(--text-tertiary, #888); cursor: pointer; font-size: 0.78rem; padding: 0; }
.ps-body { margin-top: 6px; display: flex; flex-direction: column; gap: 6px; }
.ps-help { margin: 0; font-size: 0.75rem; color: var(--text-tertiary, #777); }
.ps-actions { display: flex; gap: 6px; }
.ps-error { color: var(--accent-red, #ef4444); font-size: 0.78rem; margin: 0; }
.ps-promoted { color: var(--accent-emerald, #22c55e); font-size: 0.78rem; margin: 0; }
.ps-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
.ps-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 4px 6px; background: var(--bg-tertiary, #1a1a24); border-radius: 5px; font-size: 0.78rem; }
.ps-row.winner { border: 1px solid var(--accent-emerald, #22c55e); }
.ps-row.hard-fail { opacity: 0.6; }
.ps-name { font-family: monospace; color: var(--accent-cyan, #00d4ff); }
.ps-badge { font-size: 0.65rem; padding: 1px 6px; border-radius: 4px; }
.ps-badge-win { background: rgba(34,197,94,0.15); color: #22c55e; }
.ps-badge-fail { background: rgba(239,68,68,0.15); color: #ef4444; }
.ps-badge-merged { background: var(--bg-secondary, rgba(255,255,255,0.06)); color: var(--text-tertiary, #888); }
.ps-score { color: var(--text-secondary, #aaa); font-variant-numeric: tabular-nums; }
.ps-axes { color: var(--text-tertiary, #777); margin-left: auto; font-variant-numeric: tabular-nums; }
.ps-empty { color: var(--text-tertiary, #777); font-size: 0.78rem; margin: 0; }
</style>
