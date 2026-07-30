<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  settingsApi,
  grdSteeringApi,
  ApiError,
  type GrdSteeringProject,
  type InteractiveFallback,
} from '../../services/api';
import { useToast } from '../../composables/useToast';

const { t } = useI18n();
const showToast = useToast();

const autoInitEnabled = ref(true);
const syncOnSessionComplete = ref(true);
const defaultVerificationLevel = ref('proxy');
const isLoading = ref(true);
const isSaving = ref(false);

// GRD 0.5.0 research steering. These live in each project's own
// .planning/config.json (the file GRD reads), NOT in Agented's settings table —
// so they save per row on change rather than via the Save button below, which
// only writes settings-table keys.
const steeringProjects = ref<GrdSteeringProject[]>([]);
const steeringError = ref<string | null>(null);
const busySteeringId = ref<string | null>(null);

async function loadSteering() {
  try {
    steeringError.value = null;
    const { projects } = await grdSteeringApi.list();
    steeringProjects.value = projects || [];
  } catch (e) {
    steeringError.value =
      e instanceof ApiError ? e.message : t('settings.grd.steering.loadError');
  }
}

async function patchSteering(
  project: GrdSteeringProject,
  patch: { autonomous_mode?: boolean; interactive_fallback?: InteractiveFallback },
) {
  if (!project.configured || busySteeringId.value) return;
  busySteeringId.value = project.project_id;
  try {
    const { project: updated } = await grdSteeringApi.set(project.project_id, patch);
    const idx = steeringProjects.value.findIndex((p) => p.project_id === project.project_id);
    if (idx >= 0) steeringProjects.value[idx] = updated;
    showToast(t('settings.grd.steering.toastSaved', { name: project.project_name }), 'success');
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : t('settings.grd.steering.toastFailed');
    showToast(msg, 'error');
  } finally {
    busySteeringId.value = null;
  }
}

async function loadSettings() {
  try {
    isLoading.value = true;
    const { settings: allSettings } = await settingsApi.getAll();
    autoInitEnabled.value = allSettings['grd.auto_init_enabled'] !== 'false';
    syncOnSessionComplete.value = allSettings['grd.sync_on_complete'] !== 'false';
    defaultVerificationLevel.value = allSettings['grd.default_verification_level'] || 'proxy';
  } catch {
    // Settings may not exist yet — use defaults
  } finally {
    isLoading.value = false;
  }
}

async function saveSettings() {
  try {
    isSaving.value = true;
    await settingsApi.set('grd.auto_init_enabled', String(autoInitEnabled.value));
    await settingsApi.set('grd.sync_on_complete', String(syncOnSessionComplete.value));
    await settingsApi.set('grd.default_verification_level', defaultVerificationLevel.value);
    showToast(t('settings.grd.toastSaved'), 'success');
  } catch (e) {
    const message = e instanceof ApiError ? e.message : t('settings.grd.toastSaveFailed');
    showToast(message, 'error');
  } finally {
    isSaving.value = false;
  }
}

onMounted(async () => {
  await Promise.all([loadSettings(), loadSteering()]);
});
</script>

<template>
  <div class="tab-content">
    <div v-if="isLoading" class="loading-state">
      <div class="spinner"></div>
      <span>{{ t('settings.grd.loading') }}</span>
    </div>

    <template v-else>
      <div class="card">
        <div class="card-header">
          <h3>{{ t('settings.grd.projectInitTitle') }}</h3>
        </div>
        <div class="card-body">
          <div class="form-group toggle-group">
            <label class="toggle-label">
              <span class="toggle-text">
                <strong>{{ t('settings.grd.autoInitTitle') }}</strong>
                <span class="toggle-description">{{ t('settings.grd.autoInitDesc') }}</span>
              </span>
              <button
                role="switch"
                :aria-checked="autoInitEnabled"
                :aria-label="t('settings.grd.autoInitTitle')"
                :class="['toggle-switch', { active: autoInitEnabled }]"
                @click="autoInitEnabled = !autoInitEnabled"
              >
                <span class="toggle-knob"></span>
              </button>
            </label>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top: 1.5rem;">
        <div class="card-header">
          <h3>{{ t('settings.grd.syncBehaviorTitle') }}</h3>
        </div>
        <div class="card-body">
          <div class="form-group toggle-group">
            <label class="toggle-label">
              <span class="toggle-text">
                <strong>{{ t('settings.grd.syncOnCompleteTitle') }}</strong>
                <span class="toggle-description">{{ t('settings.grd.syncOnCompleteDesc') }}</span>
              </span>
              <button
                role="switch"
                :aria-checked="syncOnSessionComplete"
                :aria-label="t('settings.grd.syncOnCompleteTitle')"
                :class="['toggle-switch', { active: syncOnSessionComplete }]"
                @click="syncOnSessionComplete = !syncOnSessionComplete"
              >
                <span class="toggle-knob"></span>
              </button>
            </label>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top: 1.5rem;">
        <div class="card-header">
          <h3>{{ t('settings.grd.verificationLevelTitle') }}</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <select v-model="defaultVerificationLevel" class="form-select">
              <option value="sanity">{{ t('settings.grd.verificationSanity') }}</option>
              <option value="proxy">{{ t('settings.grd.verificationProxy') }}</option>
              <option value="deferred">{{ t('settings.grd.verificationDeferred') }}</option>
            </select>
            <span class="help-text">{{ t('settings.grd.verificationHelp') }}</span>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top: 1.5rem;" data-testid="grd-steering">
        <div class="card-header">
          <h3>{{ t('settings.grd.steering.title') }}</h3>
        </div>
        <div class="card-body">
          <p class="help-text" style="margin-top: 0;">{{ t('settings.grd.steering.desc') }}</p>

          <p v-if="steeringError" class="steering-error" data-testid="grd-steering-error">
            {{ steeringError }}
          </p>
          <p
            v-else-if="!steeringProjects.length"
            class="help-text"
            data-testid="grd-steering-empty"
          >
            {{ t('settings.grd.steering.noProjects') }}
          </p>

          <div
            v-for="p in steeringProjects"
            :key="p.project_id"
            class="steering-row"
            :data-testid="`grd-steering-row-${p.project_id}`"
          >
            <div class="steering-head">
              <strong>{{ p.project_name }}</strong>
              <span v-if="!p.configured" class="steering-badge" data-testid="grd-steering-unconfigured">
                {{ t('settings.grd.steering.notConfigured') }}
              </span>
            </div>
            <span v-if="p.configured" class="steering-path">{{ p.config_path }}</span>
            <span v-else class="help-text">{{ t('settings.grd.steering.notConfiguredHelp') }}</span>

            <template v-if="p.configured">
              <div class="form-group toggle-group" style="margin-top: 0.75rem;">
                <label class="toggle-label">
                  <span class="toggle-text">
                    <strong>{{ t('settings.grd.steering.autonomousTitle') }}</strong>
                    <span class="toggle-description">
                      {{ t('settings.grd.steering.autonomousDesc') }}
                    </span>
                  </span>
                  <button
                    role="switch"
                    :aria-checked="p.autonomous_mode"
                    :aria-label="t('settings.grd.steering.autonomousTitle')"
                    :disabled="busySteeringId === p.project_id"
                    :class="['toggle-switch', { active: p.autonomous_mode }]"
                    :data-testid="`grd-steering-autonomous-${p.project_id}`"
                    @click="patchSteering(p, { autonomous_mode: !p.autonomous_mode })"
                  >
                    <span class="toggle-knob"></span>
                  </button>
                </label>
              </div>

              <div class="form-group" style="margin-top: 0.75rem;">
                <label class="field-label" :for="`fallback-${p.project_id}`">
                  {{ t('settings.grd.steering.fallbackLabel') }}
                </label>
                <select
                  :id="`fallback-${p.project_id}`"
                  class="form-select"
                  :value="p.interactive_fallback"
                  :disabled="busySteeringId === p.project_id"
                  :data-testid="`grd-steering-fallback-${p.project_id}`"
                  @change="
                    patchSteering(p, {
                      interactive_fallback: ($event.target as HTMLSelectElement)
                        .value as InteractiveFallback,
                    })
                  "
                >
                  <option value="recommended">
                    {{ t('settings.grd.steering.fallbackRecommended') }}
                  </option>
                  <option value="panel">{{ t('settings.grd.steering.fallbackPanel') }}</option>
                </select>
                <span class="help-text">{{ t('settings.grd.steering.fallbackHelp') }}</span>
              </div>

              <!-- The honest status line: which of the two is actually in force. -->
              <p
                v-if="!p.interactive_enabled"
                class="steering-note"
                :data-testid="`grd-steering-note-${p.project_id}`"
              >
                {{ t('settings.grd.steering.interactiveOff') }}
              </p>
              <p
                v-else-if="p.autonomous_mode"
                class="steering-note"
                :data-testid="`grd-steering-note-${p.project_id}`"
              >
                {{ t('settings.grd.steering.noteAutonomous') }}
              </p>
              <p v-else class="steering-note" :data-testid="`grd-steering-note-${p.project_id}`">
                {{ t('settings.grd.steering.noteHuman') }}
              </p>
            </template>
          </div>
        </div>
      </div>

      <div class="form-actions" style="margin-top: 1.5rem;">
        <button class="btn btn-primary" :disabled="isSaving" @click="saveSettings">
          {{ isSaving ? t('settings.grd.saving') : t('settings.grd.saveSettings') }}
        </button>
        <span class="help-text">{{ t('settings.grd.steering.saveScopeHint') }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.card { overflow: hidden; }
.card-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem 1.25rem; border-bottom: 1px solid var(--border-default); }
.card-header h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary, #fff); margin: 0; }
.card-body { padding: 1.25rem; }
.form-group:last-child { margin-bottom: 0; }
.help-text { font-size: 0.8rem; color: var(--text-tertiary, #666); margin-top: 0.5rem; display: block; }
.toggle-group { margin-bottom: 0; }
.toggle-label { display: flex !important; align-items: center; justify-content: space-between; gap: 1rem; cursor: pointer; }
.toggle-text { display: flex; flex-direction: column; gap: 0.25rem; }
.toggle-text strong { font-size: 0.9rem; color: var(--text-primary, #fff); font-weight: 500; }
.toggle-description { font-size: 0.8rem; color: var(--text-tertiary, #666); }
.toggle-switch { position: relative; width: 44px; height: 24px; border-radius: 12px; border: none; background: var(--bg-tertiary, #1a1a24); cursor: pointer; transition: background 0.2s; flex-shrink: 0; padding: 0; }
.toggle-switch.active { background: var(--accent-cyan, #00d4ff); }
.toggle-knob { position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%; background: var(--text-primary, #fff); transition: transform 0.2s; }
.toggle-switch.active .toggle-knob { transform: translateX(20px); }
.form-select { width: 100%; padding: 0.75rem 1rem; background: var(--bg-tertiary, #1a1a24); border: 1px solid var(--border-default); border-radius: 8px; color: var(--text-primary, #fff); font-size: 0.9rem; transition: border-color 0.15s; }
.form-select:focus { outline: none; border-color: var(--accent-cyan, #00d4ff); }
.steering-row { padding: 1rem 0; border-top: 1px solid var(--border-default); }
.steering-row:first-of-type { border-top: none; padding-top: 0.5rem; }
.steering-head { display: flex; align-items: center; gap: 0.5rem; }
.steering-head strong { font-size: 0.9rem; color: var(--text-primary, #fff); font-weight: 600; }
.steering-badge { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; padding: 0.15rem 0.45rem; border-radius: 4px; background: var(--bg-tertiary, #1a1a24); color: var(--text-tertiary, #666); }
.steering-path { display: block; font-size: 0.75rem; color: var(--text-tertiary, #666); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; word-break: break-all; margin-top: 0.2rem; }
.steering-note { font-size: 0.8rem; color: var(--text-secondary, #999); margin: 0.6rem 0 0; padding-left: 0.6rem; border-left: 2px solid var(--accent-cyan, #00d4ff); }
.steering-error { font-size: 0.8rem; color: var(--accent-red, #ff5c5c); margin: 0.5rem 0 0; }
.field-label { display: block; font-size: 0.85rem; color: var(--text-primary, #fff); margin-bottom: 0.35rem; }
.form-select:disabled, .toggle-switch:disabled { opacity: 0.5; cursor: not-allowed; }
.loading-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 2rem; }
.loading-state span { color: var(--text-tertiary, #666); font-size: 0.85rem; }
.spinner { width: 32px; height: 32px; border: 3px solid var(--bg-tertiary, #1a1a24); border-top-color: var(--accent-cyan, #00d4ff); border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 1rem; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
