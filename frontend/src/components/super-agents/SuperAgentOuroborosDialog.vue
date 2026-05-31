<script setup lang="ts">
/**
 * SuperAgentOuroborosDialog — v0.7.92.
 *
 * Minimal dialog wrapping ``superAgentApi.startOuroborosRun``.
 * Operator picks a project (or leaves empty to let the backend
 * fall back to the SA's most recent project), types a goal,
 * optionally sets iteration / wall-time caps and a deterministic
 * ``check_cmd``, and the bridge spawns a goal_loop project
 * session with Ouroboros mode forced on.
 *
 * The dialog does NOT navigate after kicking off — the parent
 * decides what to do with the returned ``session_id`` (the SA
 * list page shows a toast and stays put; a future SA detail
 * page might navigate into the streaming chat).
 */
import { computed, onMounted, ref, watch } from 'vue';
import { ApiError, projectApi, superAgentApi } from '../../services/api';
import { useFocusTrap } from '../../composables/useFocusTrap';
import { useToast } from '../../composables/useToast';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

interface Project {
  id: string;
  name: string;
}

const props = defineProps<{
  visible: boolean;
  superAgentId: string;
  superAgentName: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (
    e: 'started',
    payload: {
      session_id: string;
      project_id: string;
      super_agent_id: string;
    },
  ): void;
}>();

const dialogRef = ref<HTMLElement | null>(null);
const isOpen = computed(() => props.visible);
useFocusTrap(dialogRef, isOpen);

const showToast = useToast();

const projects = ref<Project[]>([]);
const projectsLoading = ref(false);
const projectsError = ref<string | null>(null);

const goal = ref('');
// Empty string → use the backend fallback (SA's most recent
// project). Setting to a real id targets that project explicitly.
const projectId = ref('');
const maxIterations = ref(20);
const maxWallMinutes = ref(30);
const checkCmd = ref('');
const yoloMode = ref(false);
const submitting = ref(false);

const goalIsValid = computed(() => goal.value.trim().length > 0);

async function loadProjects() {
  projectsLoading.value = true;
  projectsError.value = null;
  try {
    const res = await projectApi.list({ limit: 100 });
    projects.value = res.projects.map(p => ({ id: p.id, name: p.name }));
  } catch (e) {
    projectsError.value =
      e instanceof Error ? e.message : t('superAgentOuroborosDialog.loadProjectsError');
  } finally {
    projectsLoading.value = false;
  }
}

watch(
  () => props.visible,
  v => {
    if (v) {
      // Reset between opens so a previous attempt's draft
      // doesn't leak across SAs.
      goal.value = '';
      projectId.value = '';
      maxIterations.value = 20;
      maxWallMinutes.value = 30;
      checkCmd.value = '';
      yoloMode.value = false;
      loadProjects();
    }
  },
);

onMounted(() => {
  if (props.visible) loadProjects();
});

async function submit() {
  if (!goalIsValid.value || submitting.value) return;
  submitting.value = true;
  try {
    const res = await superAgentApi.startOuroborosRun(props.superAgentId, {
      // Omit project_id entirely when the operator left it empty —
      // the backend's fallback resolver picks the SA's most-recent
      // project. Sending an empty string would trip the route's
      // truthy check.
      ...(projectId.value ? { project_id: projectId.value } : {}),
      goal: goal.value.trim(),
      max_iterations: maxIterations.value,
      max_wall_seconds: maxWallMinutes.value * 60,
      check_cmd: checkCmd.value.trim() || null,
      yolo_mode: yoloMode.value,
    });
    showToast(
      t('superAgentOuroborosDialog.runStarted', { name: props.superAgentName }),
      'success',
    );
    emit('started', {
      session_id: res.session_id,
      project_id: res.project_id,
      super_agent_id: res.super_agent_id,
    });
    emit('close');
  } catch (e: unknown) {
    let msg = t('superAgentOuroborosDialog.startError');
    if (e instanceof ApiError || e instanceof Error) {
      msg = e.message;
    }
    showToast(msg, 'error');
  } finally {
    submitting.value = false;
  }
}

function onCancel() {
  if (submitting.value) return;
  emit('close');
}
</script>

<template>
  <div
    v-if="visible"
    class="modal-backdrop"
    role="dialog"
    aria-modal="true"
    aria-labelledby="ouroboros-dialog-title"
    @click.self="onCancel"
  >
    <div ref="dialogRef" class="modal">
      <header class="modal-header">
        <h2 id="ouroboros-dialog-title">{{ t('superAgentOuroborosDialog.title', { name: superAgentName }) }}</h2>
        <button
          class="btn-close"
          type="button"
          :aria-label="t('common.close')"
          @click="onCancel"
        >
          ×
        </button>
      </header>

      <p class="modal-hint">
        {{ t('superAgentOuroborosDialog.hint') }}
      </p>

      <form class="modal-form" @submit.prevent="submit">
        <div class="form-group">
          <label for="ouroboros-goal">
            {{ t('superAgentOuroborosDialog.goal') }}
            <span class="required">*</span>
          </label>
          <textarea
            id="ouroboros-goal"
            v-model="goal"
            rows="3"
            :placeholder="t('superAgentOuroborosDialog.goalPlaceholder')"
            :disabled="submitting"
            required
          />
        </div>

        <div class="form-group">
          <label for="ouroboros-project">{{ t('superAgentOuroborosDialog.project') }}</label>
          <select
            id="ouroboros-project"
            v-model="projectId"
            :disabled="submitting || projectsLoading"
          >
            <option value="">{{ t('superAgentOuroborosDialog.useRecentProject') }}</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">
              {{ p.name }}
            </option>
          </select>
          <p v-if="projectsError" class="form-error">{{ projectsError }}</p>
          <p v-else class="form-hint">
            {{ t('superAgentOuroborosDialog.projectHint') }}
          </p>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="ouroboros-iter">{{ t('superAgentOuroborosDialog.maxIterations') }}</label>
            <input
              id="ouroboros-iter"
              v-model.number="maxIterations"
              type="number"
              min="1"
              max="200"
              :disabled="submitting"
            />
          </div>
          <div class="form-group">
            <label for="ouroboros-wall">{{ t('superAgentOuroborosDialog.maxWallTime') }}</label>
            <input
              id="ouroboros-wall"
              v-model.number="maxWallMinutes"
              type="number"
              min="1"
              max="600"
              :disabled="submitting"
            />
          </div>
        </div>

        <div class="form-group">
          <label for="ouroboros-check">
            {{ t('superAgentOuroborosDialog.checkCommand') }}
            <span class="optional">{{ t('superAgentOuroborosDialog.optional') }}</span>
          </label>
          <input
            id="ouroboros-check"
            v-model="checkCmd"
            type="text"
            :placeholder="t('superAgentOuroborosDialog.checkCommandPlaceholder')"
            :disabled="submitting"
          />
          <p class="form-hint">
            {{ t('superAgentOuroborosDialog.checkCommandHint') }}
          </p>
        </div>

        <div class="form-group toggle-group">
          <label class="row-toggle">
            <input
              v-model="yoloMode"
              type="checkbox"
              :disabled="submitting"
            />
            <span class="toggle-body">
              <span class="toggle-title">{{ t('superAgentOuroborosDialog.yoloMode') }}</span>
              <span class="toggle-sub">
                {{ t('superAgentOuroborosDialog.yoloModeSub') }}
              </span>
            </span>
          </label>
        </div>

        <footer class="modal-actions">
          <button
            type="button"
            class="btn btn-secondary"
            :disabled="submitting"
            @click="onCancel"
          >
            {{ t('common.cancel') }}
          </button>
          <button
            type="submit"
            class="btn btn-primary"
            :disabled="!goalIsValid || submitting"
          >
            {{ submitting ? t('superAgentOuroborosDialog.starting') : t('superAgentOuroborosDialog.runButton') }}
          </button>
        </footer>
      </form>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  background: var(--bg-secondary, #1a1a20);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  width: 540px;
  max-width: calc(100% - 32px);
  max-height: 90vh;
  overflow-y: auto;
  padding: 20px;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.modal-header h2 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
}
.btn-close {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  padding: 0 6px;
}
.modal-hint {
  margin: 0 0 16px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-tertiary);
}
.modal-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.form-group label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}
.form-group .required {
  color: var(--accent-red, #ff5470);
}
.form-group .optional {
  color: var(--text-tertiary);
  font-weight: 400;
}
.form-group textarea,
.form-group input[type='text'],
.form-group input[type='number'],
.form-group select {
  background: var(--bg-primary, #101015);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  padding: 8px 10px;
  font-family: inherit;
  font-size: 13px;
}
.form-group textarea {
  resize: vertical;
  min-height: 60px;
}
.form-hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.4;
}
.form-error {
  margin: 0;
  font-size: 11px;
  color: var(--accent-red, #ff5470);
}
.row-toggle {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  cursor: pointer;
}
.toggle-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.toggle-title {
  font-size: 13px;
  color: var(--text-primary);
}
.toggle-sub {
  font-size: 11px;
  color: var(--text-tertiary);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
.btn {
  padding: 8px 16px;
  border-radius: 4px;
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 13px;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.btn-primary {
  background: var(--accent-violet, #8855ff);
  color: #fff;
}
.btn-primary:hover:not(:disabled) {
  background: #9966ff;
}
.btn-secondary {
  background: transparent;
  color: var(--text-secondary);
  border-color: var(--border-default);
}
</style>
