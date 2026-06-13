<script setup lang="ts">
/**
 * AutonomyEditor (REQ-16) — reads, edits, and writes a project's autonomy
 * policy. Mirrors GrdSettings.vue form patterns. The policy is a free-form
 * Record (backend contract is loosely typed), so we render known autonomy
 * fields as form controls and write the whole policy back on save.
 */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../services/api';
import { ApiError } from '../../../services/api';
import { useToast } from '../../../composables/useToast';

const props = defineProps<{ projectId: string }>();

const { t } = useI18n();
const showToast = useToast();

const policy = ref<Record<string, unknown>>({});
const configured = ref(false);
const isLoading = ref(true);
const isSaving = ref(false);

// Known boolean autonomy levers surfaced as toggles; unknown keys are preserved.
const autoPlan = ref(false);
const autoExecute = ref(false);
const autoVerify = ref(false);
const maxRounds = ref<number>(0);

function hydrateFromPolicy(p: Record<string, unknown>) {
  policy.value = { ...p };
  autoPlan.value = Boolean(p.auto_plan);
  autoExecute.value = Boolean(p.auto_execute);
  autoVerify.value = Boolean(p.auto_verify);
  maxRounds.value = typeof p.max_rounds === 'number' ? p.max_rounds : 0;
}

async function load() {
  try {
    isLoading.value = true;
    const res = await grdHarnessApi.getAutonomy(props.projectId);
    configured.value = res.configured;
    hydrateFromPolicy(res.policy || {});
  } catch {
    // No policy yet — start from empty defaults.
  } finally {
    isLoading.value = false;
  }
}

async function save() {
  try {
    isSaving.value = true;
    const next: Record<string, unknown> = {
      ...policy.value,
      auto_plan: autoPlan.value,
      auto_execute: autoExecute.value,
      auto_verify: autoVerify.value,
      max_rounds: maxRounds.value,
    };
    await grdHarnessApi.setAutonomy(props.projectId, next);
    policy.value = next;
    configured.value = true;
    showToast(t('surface.harness.autonomy.saved'), 'success');
  } catch (e) {
    const message = e instanceof ApiError ? e.message : t('surface.harness.autonomy.saveFailed');
    showToast(message, 'error');
  } finally {
    isSaving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="card autonomy-editor">
    <div class="card-header">
      <h3>{{ t('surface.harness.autonomy.title') }}</h3>
      <span v-if="!configured" class="badge">{{ t('surface.harness.autonomy.unconfigured') }}</span>
    </div>
    <div v-if="isLoading" class="card-body">
      <span class="muted">{{ t('surface.harness.autonomy.loading') }}</span>
    </div>
    <div v-else class="card-body">
      <label class="toggle-row">
        <span>{{ t('surface.harness.autonomy.autoPlan') }}</span>
        <button :class="['toggle', { active: autoPlan }]" @click="autoPlan = !autoPlan"></button>
      </label>
      <label class="toggle-row">
        <span>{{ t('surface.harness.autonomy.autoExecute') }}</span>
        <button
          :class="['toggle', { active: autoExecute }]"
          @click="autoExecute = !autoExecute"
        ></button>
      </label>
      <label class="toggle-row">
        <span>{{ t('surface.harness.autonomy.autoVerify') }}</span>
        <button
          :class="['toggle', { active: autoVerify }]"
          @click="autoVerify = !autoVerify"
        ></button>
      </label>
      <label class="field-row">
        <span>{{ t('surface.harness.autonomy.maxRounds') }}</span>
        <input v-model.number="maxRounds" type="number" min="0" class="num-input" />
      </label>
      <div class="actions">
        <button class="btn btn-primary" :disabled="isSaving" @click="save">
          {{ isSaving ? t('surface.harness.autonomy.saving') : t('surface.harness.autonomy.save') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.autonomy-editor { border: 1px solid var(--border-default); border-radius: 8px; }
.card-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.25rem; border-bottom: 1px solid var(--border-default); }
.card-header h3 { font-size: 0.95rem; margin: 0; color: var(--text-primary, #fff); }
.card-body { padding: 1.25rem; display: flex; flex-direction: column; gap: 1rem; }
.toggle-row, .field-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.toggle-row span, .field-row span { color: var(--text-secondary, #aaa); font-size: 0.9rem; }
.toggle { position: relative; width: 44px; height: 24px; border-radius: 12px; border: none; background: var(--bg-tertiary, #1a1a24); cursor: pointer; }
.toggle.active { background: var(--accent-cyan, #00d4ff); }
.num-input { width: 90px; padding: 0.5rem; background: var(--bg-tertiary, #1a1a24); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-primary, #fff); }
.actions { display: flex; justify-content: flex-end; }
.badge { font-size: 0.7rem; color: var(--text-tertiary, #666); border: 1px solid var(--border-default); border-radius: 4px; padding: 2px 6px; }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
