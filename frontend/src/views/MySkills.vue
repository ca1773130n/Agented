<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import type { SkillInfo, UserSkill } from '../services/api';
import { skillsApi, userSkillsApi, ApiError } from '../services/api';
import PageLayout from '../components/base/PageLayout.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpPageTools } from '../webmcp/useWebMcpPageTools';

const props = defineProps<{
  highlightId?: string | null;
}>();

const router = useRouter();
const showToast = useToast();

const discoveredSkills = ref<SkillInfo[]>([]);
const userSkills = ref<UserSkill[]>([]);
const isLoading = ref(true);
const searchQuery = ref('');
const showAddModal = ref(false);

const addModalRef = ref<HTMLElement | null>(null);
useFocusTrap(addModalRef, showAddModal);

useWebMcpPageTools({
  page: 'MySkills',
  domain: 'skills',
  stateGetter: () => ({
    items: userSkills.value,
    itemCount: userSkills.value.length,
    isLoading: isLoading.value,
    error: null,
    searchQuery: searchQuery.value,
    discoveredSkillsCount: discoveredSkills.value.length,
  }),
  modalGetter: () => ({
    showCreateModal: showAddModal.value,
    showDeleteConfirm: false,
  }),
  deps: [userSkills, discoveredSkills, searchQuery],
});

// Highlight support — must be after userSkills ref declaration
function tryHighlight() {
  const id = props.highlightId;
  if (!id || userSkills.value.length === 0) return;
  const skill = userSkills.value.find(s => s.skill_name === id);
  if (skill) {
    router.push({ name: 'skill-detail', params: { skillId: skill.id } });
    nextTick(() => {
      const el = document.getElementById(`entity-${skill.id}`) || document.querySelector(`[data-entity-name="${id}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('highlight-pulse');
        setTimeout(() => el.classList.remove('highlight-pulse'), 2000);
      }
    });
  }
}
watch(() => props.highlightId, tryHighlight);
watch(() => userSkills.value.length, tryHighlight);

const filteredDiscoveredSkills = computed(() => {
  const q = searchQuery.value.toLowerCase();
  const userSkillNames = new Set(userSkills.value.map(s => s.skill_name));
  return discoveredSkills.value
    .filter(s => !userSkillNames.has(s.name))
    .filter(s => !q || s.name.toLowerCase().includes(q) || (s.description && s.description.toLowerCase().includes(q)));
});

async function loadData() {
  isLoading.value = true;
  try {
    const [discovered, user] = await Promise.all([
      skillsApi.list(),
      userSkillsApi.list()
    ]);
    discoveredSkills.value = discovered.skills || [];
    userSkills.value = user.skills || [];
  } catch (e) {
    showToast('Failed to load skills', 'error');
  } finally {
    isLoading.value = false;
  }
}

async function addSkill(skill: SkillInfo) {
  try {
    await userSkillsApi.add({
      skill_name: skill.name,
      skill_path: skill.source_path || '',
      description: skill.description || ''
    });
    showToast(`Skill "${skill.name}" added`, 'success');
    showAddModal.value = false;
    await loadData();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to add skill', 'error');
    }
  }
}

async function removeSkill(skill: UserSkill) {
  try {
    await userSkillsApi.delete(skill.id);
    showToast(`Skill "${skill.skill_name}" removed`, 'success');
    await loadData();
  } catch (e) {
    showToast('Failed to remove skill', 'error');
  }
}

async function toggleEnabled(skill: UserSkill) {
  try {
    await userSkillsApi.update(skill.id, { enabled: skill.enabled ? 0 : 1 });
    await loadData();
  } catch (e) {
    showToast('Failed to update skill', 'error');
  }
}

async function toggleHarness(skill: UserSkill) {
  try {
    await userSkillsApi.update(skill.id, { selected_for_harness: skill.selected_for_harness ? 0 : 1 });
    await loadData();
    showToast(
      skill.selected_for_harness ? 'Removed from harness' : 'Added to harness',
      'success'
    );
  } catch (e) {
    showToast('Failed to update skill', 'error');
  }
}

onMounted(() => {
  loadData();
});
</script>

<template>
  <PageLayout :breadcrumbs="[{ label: 'Skills' }]">
    <PageHeader title="Skill Library" subtitle="Manage your collection of Claude skills">
      <template #actions>
        <button class="btn btn-primary" @click="showAddModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Add Skill
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading skills..." />

    <EmptyState
      v-else-if="userSkills.length === 0"
      title="No skills configured"
      description="Add skills from discovered skills to manage them here"
    >
      <template #icon>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/>
          <path d="M2 17l10 5 10-5"/>
          <path d="M2 12l10 5 10-5"/>
        </svg>
      </template>
      <template #actions>
        <button class="btn btn-primary" @click="showAddModal = true">Add Your First Skill</button>
      </template>
    </EmptyState>

    <div v-else class="skills-grid">
      <div v-for="skill in userSkills" :key="skill.id" :id="'entity-' + skill.id" :data-entity-name="skill.skill_name" class="skill-card" :class="{ disabled: !skill.enabled }" @click="router.push({ name: 'skill-detail', params: { skillId: skill.id } })">
        <div class="skill-header">
          <div class="skill-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div class="skill-info">
            <h3>{{ skill.skill_name }}</h3>
            <span class="skill-path">{{ skill.skill_path }}</span>
          </div>
        </div>

        <p v-if="skill.description" class="skill-description">{{ skill.description }}</p>

        <div class="skill-toggles">
          <label class="toggle-row">
            <span>Enabled</span>
            <button class="toggle-btn" :class="{ active: skill.enabled }" @click.stop="toggleEnabled(skill)">
              <span class="toggle-knob"></span>
            </button>
          </label>
          <label class="toggle-row">
            <div class="toggle-label">
              <span>Include to Harness</span>
              <span class="toggle-hint">Bundle into harness plugin config for deployment</span>
            </div>
            <button class="toggle-btn" :class="{ active: skill.selected_for_harness }" @click.stop="toggleHarness(skill)">
              <span class="toggle-knob"></span>
            </button>
          </label>
        </div>

        <div class="skill-actions">
          <button class="btn btn-small btn-danger" @click.stop="removeSkill(skill)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            Remove
          </button>
        </div>
      </div>
    </div>

    <!-- Add Skill Modal -->
    <Teleport to="body">
      <div v-if="showAddModal" ref="addModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-skill-library" tabindex="-1" @click.self="showAddModal = false" @keydown.escape="showAddModal = false">
        <div class="modal add-skill-modal">
          <div class="modal-header">
            <h2 id="modal-title-add-skill-library">Add Skill</h2>
            <button class="btn-close" @click="showAddModal = false">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>

          <div class="modal-search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35"/>
            </svg>
            <input v-model="searchQuery" type="text" placeholder="Search discovered skills..." />
          </div>

          <div class="discovered-skills-list">
            <div v-if="filteredDiscoveredSkills.length === 0" class="no-skills">
              <p>No skills available to add</p>
            </div>
            <div
              v-for="skill in filteredDiscoveredSkills"
              :key="skill.name"
              class="discovered-skill-item"
            >
              <div class="skill-info">
                <span class="skill-name">{{ skill.name }}</span>
                <span v-if="skill.description" class="skill-desc">{{ skill.description }}</span>
              </div>
              <button class="btn btn-small btn-primary" @click="addSkill(skill)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 5v14M5 12h14"/>
                </svg>
                Add
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </PageLayout>
</template>

<style scoped>
.skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 20px;
}

.skill-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
  transition: border-color 0.2s;
  cursor: pointer;
}

.skill-card:hover {
  border-color: var(--border-strong);
}

.skill-card.disabled {
  opacity: 0.6;
}

.skill-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.skill-icon {
  width: 44px;
  height: 44px;
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.skill-icon svg {
  width: 24px;
  height: 24px;
  color: var(--accent-violet, #8855ff);
}

.skill-info {
  flex: 1;
  min-width: 0;
}

.skill-info h3 {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.skill-path {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  word-break: break-all;
}

.skill-description {
  color: var(--text-secondary);
  font-size: 14px;
  margin: 0 0 16px 0;
  line-height: 1.5;
}

.skill-toggles {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 0;
  border-top: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 16px;
}

.toggle-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: var(--text-secondary);
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

.skill-actions {
  display: flex;
  gap: 8px;
}

.btn-small {
  padding: 6px 12px;
  font-size: 13px;
}

/* Add Skill Modal */
.add-skill-modal {
  max-width: 500px;
  width: 90%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.modal-header h2 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.btn-close {
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.15s;
}

.btn-close:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-close svg {
  width: 18px;
  height: 18px;
}

.modal-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 16px 24px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.modal-search svg {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.modal-search input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
}

.modal-search input::placeholder {
  color: var(--text-tertiary);
}

.discovered-skills-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 24px 24px;
}

.no-skills {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-tertiary);
}

.discovered-skill-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px;
  border-radius: 8px;
  transition: background 0.15s;
}

.discovered-skill-item:hover {
  background: var(--bg-tertiary);
}

.discovered-skill-item .skill-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.discovered-skill-item .skill-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.discovered-skill-item .skill-desc {
  font-size: 12px;
  color: var(--text-tertiary);
}
</style>
