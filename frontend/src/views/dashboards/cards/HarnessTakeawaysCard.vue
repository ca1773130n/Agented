<!--
  HarnessTakeawaysCard — positive-learning surface (inverse of the
  failure-layer card). Lists recent takeaways extracted from every
  completed session, with Apply / Dismiss inline.

  Takeaways auto-apply only when AGENTED_TAKEAWAY_AUTOAPPLY=1 on the
  backend and confidence >= 0.85. Otherwise they queue here for operator
  review.
-->
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import {
  harnessTakeawaysApi,
  TAKEAWAY_KIND_LABEL,
  TAKEAWAY_TARGET_COLOR_VAR,
  TAKEAWAY_TARGET_LABEL,
  type Takeaway,
} from '../../../services/api/harness-takeaways';
import LoadingState from '../../../components/base/LoadingState.vue';
import ErrorState from '../../../components/base/ErrorState.vue';

const emit = defineEmits<{ loaded: [slug: string] }>();

const isLoading = ref(false);
const loadError = ref<string | null>(null);
const takeaways = ref<Takeaway[]>([]);
const actingId = ref<string | null>(null);
const actionError = ref<string | null>(null);
const showAll = ref(false);

const visibleTakeaways = computed(() =>
  showAll.value
    ? takeaways.value
    : takeaways.value.filter((t) => !t.applied && !t.dismissed),
);
const isEmpty = computed(() => visibleTakeaways.value.length === 0);

async function loadData() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const res = await harnessTakeawaysApi.listRecent({ limit: 25 });
    takeaways.value = res?.takeaways || [];
  } catch (err) {
    loadError.value =
      err instanceof Error ? err.message : 'Failed to load takeaways';
    takeaways.value = [];
  } finally {
    isLoading.value = false;
    emit('loaded', 'harness-takeaways');
  }
}

async function applyOne(tk: Takeaway) {
  if (actingId.value) return;
  actingId.value = tk.id;
  actionError.value = null;
  try {
    const res = await harnessTakeawaysApi.apply(tk.id);
    if (!res.applied) {
      actionError.value = res.reason || 'Apply failed';
    }
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : 'Apply failed';
  } finally {
    actingId.value = null;
    await loadData();
  }
}

async function dismissOne(tk: Takeaway) {
  if (actingId.value) return;
  actingId.value = tk.id;
  actionError.value = null;
  try {
    const res = await harnessTakeawaysApi.dismiss(tk.id, 'operator rejected');
    if (!res.dismissed) {
      actionError.value = res.reason || 'Dismiss failed';
    }
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : 'Dismiss failed';
  } finally {
    actingId.value = null;
    await loadData();
  }
}

function fmtConfidence(v: number): string {
  return `${Math.round(v * 100)}%`;
}

onMounted(loadData);
</script>

<template>
  <section
    id="harness-takeaways"
    class="lane-card"
    data-testid="harness-takeaways-card"
  >
    <header class="lane-card__head">
      <div>
        <h2 class="lane-card__title">Session takeaways</h2>
        <p class="lane-card__subtitle">
          What sessions taught us — user preferences, discovered procedures,
          domain facts. Apply to memory / rules / KG, or dismiss.
        </p>
      </div>
      <label class="head-toggle">
        <input type="checkbox" v-model="showAll" />
        <span>Show applied / dismissed</span>
      </label>
    </header>

    <LoadingState v-if="isLoading" message="Loading…" />
    <ErrorState v-else-if="loadError" :message="loadError" @retry="loadData" />
    <p v-else-if="isEmpty" class="empty" data-testid="takeaways-empty">
      No pending takeaways. Sessions haven't surfaced anything yet — or
      you've reviewed them all.
    </p>
    <template v-else>
      <p v-if="actionError" class="action-error" role="alert">
        {{ actionError }}
      </p>
      <ul class="takeaways">
        <li
          v-for="tk in visibleTakeaways"
          :key="tk.id"
          class="tk"
          :data-testid="`takeaway-${tk.id}`"
          :data-applied="tk.applied"
          :data-dismissed="tk.dismissed"
        >
          <header class="tk__head">
            <span class="tk__kind">{{ TAKEAWAY_KIND_LABEL[tk.kind] }}</span>
            <span
              v-if="tk.suggested_target"
              class="tk__target"
              :style="{ background: TAKEAWAY_TARGET_COLOR_VAR[tk.suggested_target] }"
            >→ {{ TAKEAWAY_TARGET_LABEL[tk.suggested_target] }}</span>
            <span class="tk__confidence">{{ fmtConfidence(tk.confidence) }}</span>
            <span v-if="tk.project_id" class="tk__project">
              <code>{{ tk.project_id }}</code>
            </span>
            <span class="tk__when">{{ tk.created_at }}</span>
          </header>
          <p class="tk__content">{{ tk.content }}</p>
          <footer class="tk__foot">
            <span
              v-if="tk.applied"
              class="tk__badge tk__badge--applied"
            >applied → {{ tk.applied_target }} #{{ tk.applied_asset_id }}</span>
            <span
              v-else-if="tk.dismissed"
              class="tk__badge tk__badge--dismissed"
            >dismissed{{ tk.dismissed_reason ? `: ${tk.dismissed_reason}` : '' }}</span>
            <template v-else>
              <button
                class="btn btn-apply"
                :disabled="actingId === tk.id || !tk.suggested_target ||
                          tk.suggested_target === 'claude_md'"
                :data-testid="`takeaway-apply-${tk.id}`"
                @click="applyOne(tk)"
              >Apply</button>
              <button
                class="btn btn-dismiss"
                :disabled="actingId === tk.id"
                :data-testid="`takeaway-dismiss-${tk.id}`"
                @click="dismissOne(tk)"
              >Dismiss</button>
              <span
                v-if="tk.suggested_target === 'claude_md'"
                class="tk__manual-hint"
              >Apply manually (no auto-writer for CLAUDE.md yet)</span>
            </template>
          </footer>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.lane-card {
  padding: 20px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 10px;
  background: var(--bg-secondary, rgba(255, 255, 255, 0.02));
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.lane-card__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.lane-card__title { font-size: 14px; font-weight: 600; margin: 0; color: var(--text-primary); }
.lane-card__subtitle { font-size: 12px; margin: 4px 0 0; color: var(--text-tertiary); }

.head-toggle {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 11px;
  color: var(--text-tertiary);
  cursor: pointer;
  user-select: none;
}

.empty { font-size: 12px; color: var(--text-tertiary); margin: 0; }
.action-error { font-size: 12px; color: var(--accent-red, #ef4444); margin: 0; }

.takeaways { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.tk {
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.03));
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tk[data-applied='true'] { opacity: 0.7; }
.tk[data-dismissed='true'] { opacity: 0.5; }

.tk__head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 11px; }
.tk__kind {
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.tk__target {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  color: white;
  letter-spacing: 0.04em;
}
.tk__confidence {
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: var(--text-tertiary);
  padding: 1px 5px;
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 3px;
}
.tk__project { font-size: 10px; color: var(--text-tertiary); }
.tk__project code { font-family: var(--font-mono, monospace); }
.tk__when { font-size: 10px; color: var(--text-tertiary); margin-left: auto; }

.tk__content { font-size: 12px; color: var(--text-primary); margin: 0; white-space: pre-wrap; }

.tk__foot { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.tk__badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  letter-spacing: 0.04em;
}
.tk__badge--applied { background: var(--accent-green, #10b981); color: white; }
.tk__badge--dismissed { background: var(--text-tertiary, #6b7280); color: white; }
.tk__manual-hint { font-size: 10px; color: var(--text-tertiary); }

.btn {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.12));
  background: var(--bg-secondary, transparent);
  color: var(--text-primary);
  cursor: pointer;
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-apply { border-color: var(--accent-green, #10b981); color: var(--accent-green, #10b981); }
.btn-dismiss { border-color: var(--accent-red, #ef4444); color: var(--accent-red, #ef4444); }
</style>
