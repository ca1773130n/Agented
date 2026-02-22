<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { UserSkill } from '../services/api';
import { userSkillsApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = defineProps<{
  skillId?: number;
}>();

const route = useRoute();
const router = useRouter();
const skillId = computed(() => Number(route.params.skillId) || props.skillId || 0);

const showToast = useToast();

const skill = ref<UserSkill | null>(null);
const isSaving = ref(false);

// Editable fields
const editName = ref('');
const editDescription = ref('');
const editPath = ref('');
const editEnabled = ref(false);
const editHarness = ref(false);
const showDeleteConfirm = ref(false);

const parsedMetadata = computed(() => {
  if (!skill.value?.metadata) return null;
  try {
    return typeof skill.value.metadata === 'string'
      ? JSON.parse(skill.value.metadata)
      : skill.value.metadata;
  } catch { return null; }
});

useWebMcpTool({
  name: 'hive_skill_detail_get_state',
  description: 'Returns the current state of the SkillDetailPage',
  page: 'SkillDetailPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'SkillDetailPage',
        skillId: skill.value?.id ?? null,
        skillName: skill.value?.skill_name ?? null,
        isSaving: isSaving.value,
        enabled: editEnabled.value,
        selectedForHarness: editHarness.value,
        hasMetadata: !!parsedMetadata.value,
        showDeleteConfirm: showDeleteConfirm.value,
      }),
    }],
  }),
  deps: [skill, isSaving, editEnabled, editHarness, parsedMetadata, showDeleteConfirm],
});

async function loadSkill() {
  const data = await userSkillsApi.get(skillId.value);
  skill.value = data.skill || null;
  if (skill.value) {
    editName.value = skill.value.skill_name;
    editDescription.value = skill.value.description || '';
    editPath.value = skill.value.skill_path;
    editEnabled.value = !!skill.value.enabled;
    editHarness.value = !!skill.value.selected_for_harness;
  }
  return skill.value;
}

async function saveSkill() {
  if (!skill.value) return;
  isSaving.value = true;
  try {
    await userSkillsApi.update(skill.value.id, {
      skill_name: editName.value,
      skill_path: editPath.value,
      description: editDescription.value,
      enabled: editEnabled.value ? 1 : 0,
      selected_for_harness: editHarness.value ? 1 : 0,
    });
    showToast('Skill updated', 'success');
    await loadSkill();
  } catch (e) {
    const msg = e instanceof ApiError ? e.message : 'Failed to save skill';
    showToast(msg, 'error');
  } finally {
    isSaving.value = false;
  }
}

function deleteSkill() {
  if (!skill.value) return;
  showDeleteConfirm.value = true;
}

async function confirmDeleteSkill() {
  showDeleteConfirm.value = false;
  if (!skill.value) return;
  try {
    await userSkillsApi.delete(skill.value.id);
    showToast('Skill removed', 'success');
    router.push({ name: 'my-skills' });
  } catch {
    showToast('Failed to remove skill', 'error');
  }
}


</script>

<template>
  <EntityLayout :load-entity="loadSkill" entity-label="skill">
    <template #default="{ reload: _reload }">
    <div class="skill-detail-page">
    <AppBreadcrumb :items="[{ label: 'Skills', action: () => router.push({ name: 'my-skills' }) }, { label: skill?.skill_name || 'Skill' }]" />

    <template v-if="skill">
      <PageHeader :title="skill.skill_name || 'Skill'" :subtitle="skill.description">
        <template #actions>
          <button class="btn btn-danger" @click="deleteSkill">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            Remove
          </button>
        </template>
      </PageHeader>

      <div class="detail-card">

        <div class="form-group">
          <label>Name</label>
          <input v-model="editName" type="text" />
        </div>

        <div class="form-group">
          <label>Path</label>
          <input v-model="editPath" type="text" class="mono" />
        </div>

        <div class="form-group">
          <label>Description</label>
          <textarea v-model="editDescription" rows="4"></textarea>
        </div>

        <div v-if="parsedMetadata" class="metadata-section">
          <div v-if="parsedMetadata.triggers?.length" class="meta-group">
            <label>Triggers</label>
            <div class="meta-tags">
              <span v-for="trigger in parsedMetadata.triggers" :key="trigger" class="meta-tag">{{ trigger }}</span>
            </div>
          </div>
          <div v-if="parsedMetadata.examples?.length" class="meta-group">
            <label>Examples</label>
            <ul class="meta-list">
              <li v-for="example in parsedMetadata.examples" :key="example">{{ example }}</li>
            </ul>
          </div>
        </div>

        <div class="toggle-section">
          <label class="toggle-row">
            <span>Enabled</span>
            <button class="toggle-btn" :class="{ active: editEnabled }" @click="editEnabled = !editEnabled">
              <span class="toggle-knob"></span>
            </button>
          </label>
          <label class="toggle-row">
            <div class="toggle-label">
              <span>Include to Harness</span>
              <span class="toggle-hint">When enabled, this skill is bundled into the harness plugin configuration for deployment</span>
            </div>
            <button class="toggle-btn" :class="{ active: editHarness }" @click="editHarness = !editHarness">
              <span class="toggle-knob"></span>
            </button>
          </label>
        </div>

        <div class="form-actions">
          <button class="btn" @click="router.push({ name: 'my-skills' })">Cancel</button>
          <button class="btn btn-primary" :disabled="isSaving" @click="saveSkill">
            {{ isSaving ? 'Saving...' : 'Save Changes' }}
          </button>
        </div>
      </div>
    </template>

    <ConfirmModal
      :open="showDeleteConfirm"
      title="Remove Skill"
      message="Remove this skill from your library?"
      confirm-label="Remove"
      variant="danger"
      @confirm="confirmDeleteSkill"
      @cancel="showDeleteConfirm = false"
    />
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.skill-detail-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 800px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.detail-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 32px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.form-group input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.form-group input.mono {
  font-family: var(--font-mono);
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
}

.metadata-section {
  padding: 16px 0;
  border-top: 1px solid var(--border-subtle);
  margin-bottom: 4px;
}

.meta-group {
  margin-bottom: 16px;
}

.meta-group:last-child {
  margin-bottom: 0;
}

.meta-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.meta-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.meta-tag {
  display: inline-flex;
  padding: 4px 10px;
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.1));
  color: var(--accent-cyan);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.meta-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.toggle-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.toggle-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 400;
}

.toggle-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px 0;
  border-top: 1px solid var(--border-subtle);
  margin-bottom: 24px;
}

.toggle-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: var(--text-secondary);
}

.toggle-btn {
  width: 44px;
  height: 24px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 2px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.toggle-btn.active {
  background: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.toggle-knob {
  display: block;
  width: 18px;
  height: 18px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle-btn.active .toggle-knob {
  transform: translateX(20px);
}
</style>
