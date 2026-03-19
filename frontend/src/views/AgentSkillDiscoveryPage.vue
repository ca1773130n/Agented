<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { skillsApi, agentApi, ApiError } from '../services/api';
import type { SkillInfo, Agent } from '../services/api';

const isLoading = ref(true);
const loadError = ref<string | null>(null);
const skills = ref<SkillInfo[]>([]);
const agents = ref<Agent[]>([]);

const searchQuery = ref('');
const selectedCategory = ref<string>('all');
const addedSkills = ref<Set<string>>(new Set());

onMounted(async () => {
  try {
    const [skillsResp, agentsResp] = await Promise.all([
      skillsApi.list(),
      agentApi.list(),
    ]);
    skills.value = skillsResp.skills;
    agents.value = agentsResp.agents;
  } catch (err) {
    if (err instanceof ApiError) {
      loadError.value = `Failed to load: ${err.message}`;
    } else {
      loadError.value = 'An unexpected error occurred while loading data.';
    }
  } finally {
    isLoading.value = false;
  }
});

// Derive categories from loaded skills
const allCategories = computed(() => {
  const cats = new Set<string>();
  for (const skill of skills.value) {
    // Use a simple category derivation from skill path or name
    const cat = deriveCategory(skill);
    cats.add(cat);
  }
  return Array.from(cats).sort();
});

function deriveCategory(skill: SkillInfo): string {
  const name = (skill.name || '').toLowerCase();
  if (name.includes('security') || name.includes('audit') || name.includes('scan')) return 'security';
  if (name.includes('test') || name.includes('coverage')) return 'testing';
  if (name.includes('review') || name.includes('lint') || name.includes('code')) return 'code-review';
  if (name.includes('deploy') || name.includes('infra')) return 'deployment';
  if (name.includes('git') || name.includes('branch') || name.includes('commit')) return 'git';
  return 'general';
}

// Precompute category per skill to avoid repeated deriveCategory calls in templates
const skillCategoryMap = computed(() => {
  const map = new Map<string, string>();
  for (const skill of skills.value) {
    map.set(skill.name, deriveCategory(skill));
  }
  return map;
});

const filteredSkills = computed(() => {
  return skills.value.filter(skill => {
    const cat = skillCategoryMap.value.get(skill.name) ?? 'general';
    const matchesCategory = selectedCategory.value === 'all' || cat === selectedCategory.value;
    const matchesSearch =
      searchQuery.value.trim() === '' ||
      (skill.name || '').toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      (skill.description || '').toLowerCase().includes(searchQuery.value.toLowerCase());
    return matchesCategory && matchesSearch;
  });
});

const categoryLabel: Record<string, string> = {
  git: 'Git',
  'code-review': 'Code Review',
  security: 'Security',
  testing: 'Testing',
  deployment: 'Deployment',
  general: 'General',
};

function toggleAddToPrompt(skill: SkillInfo) {
  const key = skill.name;
  if (addedSkills.value.has(key)) {
    addedSkills.value.delete(key);
  } else {
    addedSkills.value.add(key);
  }
}

function isAdded(skill: SkillInfo): boolean {
  return addedSkills.value.has(skill.name);
}

// Show which agents could use each skill
function agentsForSkill(skill: SkillInfo): Agent[] {
  // Match agents that reference this skill in their skills array
  return agents.value.filter(
    (a) => a.skills && a.skills.some((s) => s.toLowerCase().includes(skill.name.toLowerCase()))
  );
}
</script>

<template>
  <div class="skill-discovery">

    <PageHeader
      title="Skill Auto-Discovery"
      subtitle="Automatically detect and index skills from connected repositories and plugin registries."
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="card" style="padding: 48px; text-align: center;">
      <span style="color: var(--text-tertiary); font-size: 0.85rem;">Loading skills and agents...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="card" style="padding: 48px; text-align: center;">
      <span style="color: #ef4444; font-size: 0.85rem;">{{ loadError }}</span>
    </div>

    <template v-else>
      <!-- Agents Overview -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <circle cx="12" cy="7" r="4"/>
              <path d="M5 21v-2a7 7 0 0 1 14 0v2"/>
            </svg>
            Agents ({{ agents.length }})
          </h3>
        </div>
        <div v-if="agents.length === 0" class="skills-empty" style="padding: 24px;">
          No agents configured yet.
        </div>
        <div v-else class="sources-list">
          <div v-for="agent in agents" :key="agent.id" class="source-row">
            <div class="source-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
                <circle cx="12" cy="7" r="4"/>
                <path d="M5 21v-2a7 7 0 0 1 14 0v2"/>
              </svg>
            </div>
            <div class="source-info">
              <span class="source-name">{{ agent.name }}</span>
              <span class="source-url">{{ agent.role || agent.backend_type || 'general' }}</span>
            </div>
            <div class="source-meta">
              <span class="source-stat">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12">
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                </svg>
                {{ agent.backend_type || 'claude' }}
              </span>
              <span class="source-scanned">{{ agent.description || 'No description' }}</span>
            </div>
            <div class="source-status">
              <span :class="['status-badge', agent.enabled === 1 ? 'active' : 'error']">
                {{ agent.enabled === 1 ? 'Active' : 'Disabled' }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Skill Browser -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            Discovered Skills
          </h3>
          <span class="skill-count-badge">{{ filteredSkills.length }} of {{ skills.length }}</span>
        </div>

        <!-- Search & Filter -->
        <div class="filter-bar">
          <div class="search-wrap">
            <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="15" height="15">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              v-model="searchQuery"
              type="text"
              class="search-input"
              placeholder="Search skills by name or description..."
            />
          </div>
          <select v-model="selectedCategory" class="category-select">
            <option value="all">All Categories</option>
            <option v-for="cat in allCategories" :key="cat" :value="cat">{{ categoryLabel[cat] || cat }}</option>
          </select>
        </div>

        <!-- Skills Grid -->
        <div class="skills-grid">
          <div
            v-for="skill in filteredSkills"
            :key="skill.name"
            class="skill-card"
            :class="{ 'is-added': isAdded(skill) }"
          >
            <div class="skill-card-top">
              <span :class="['category-badge', deriveCategory(skill)]">{{ categoryLabel[deriveCategory(skill)] || deriveCategory(skill) }}</span>
              <span v-if="isAdded(skill)" class="added-indicator">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="11" height="11">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                Added
              </span>
            </div>
            <div class="skill-name">{{ skill.name }}</div>
            <div class="skill-source">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="11" height="11">
                <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
              </svg>
              {{ skill.source_path || 'discovered' }}
            </div>
            <div class="skill-description">{{ skill.description || 'No description available' }}</div>
            <div v-if="agentsForSkill(skill).length > 0" class="skill-source" style="margin-top: 4px; color: var(--accent-cyan);">
              Used by: {{ agentsForSkill(skill).map(a => a.name).join(', ') }}
            </div>
            <div class="skill-footer">
              <span class="usage-count">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                </svg>
                {{ agentsForSkill(skill).length }} agent(s)
              </span>
              <button
                :class="['btn', isAdded(skill) ? 'btn-added' : 'btn-add']"
                @click="toggleAddToPrompt(skill)"
              >
                <svg v-if="!isAdded(skill)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <line x1="12" y1="5" x2="12" y2="19"/>
                  <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                {{ isAdded(skill) ? 'Remove' : 'Add to Prompt' }}
              </button>
            </div>
          </div>
          <div v-if="filteredSkills.length === 0" class="skills-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="28" height="28">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            No skills match your search
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.skill-discovery {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

/* Sources */
.sources-list {
  display: flex;
  flex-direction: column;
}

.source-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}

.source-row:hover { background: var(--bg-tertiary); }
.source-row:last-child { border-bottom: none; }

.source-icon {
  color: var(--text-muted);
  flex-shrink: 0;
}

.source-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 160px;
}

.source-name {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-primary);
}

.source-url {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-family: 'Geist Mono', monospace;
}

.source-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.source-stat {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.source-stat svg { color: var(--accent-cyan); }

.source-scanned {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.source-status {
  min-width: 90px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.status-badge.active { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.status-badge.scanning { background: rgba(99, 179, 237, 0.15); color: var(--accent-cyan); }
.status-badge.error { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-cyan);
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

/* Filter bar */
.filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-subtle);
}

.search-wrap {
  position: relative;
  flex: 1;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 8px 12px 8px 34px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 7px;
  color: var(--text-primary);
  font-size: 0.875rem;
  box-sizing: border-box;
}

.search-input::placeholder { color: var(--text-muted); }
.search-input:focus { outline: none; border-color: var(--accent-cyan); }

.category-select {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 7px;
  color: var(--text-primary);
  font-size: 0.875rem;
  cursor: pointer;
}

.category-select:focus { outline: none; border-color: var(--accent-cyan); }

/* Skills grid */
.skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1px;
  background: var(--border-subtle);
}

.skill-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 20px;
  background: var(--bg-secondary);
  transition: background 0.1s;
}

.skill-card:hover { background: var(--bg-tertiary); }
.skill-card.is-added { background: rgba(99, 179, 237, 0.04); }

.skill-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.category-badge {
  font-size: 0.68rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.category-badge.git { background: rgba(139, 92, 246, 0.15); color: #a78bfa; }
.category-badge.code-review { background: rgba(99, 179, 237, 0.15); color: var(--accent-cyan); }
.category-badge.security { background: rgba(239, 68, 68, 0.15); color: #f87171; }
.category-badge.testing { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.category-badge.deployment { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.category-badge.general { background: rgba(156, 163, 175, 0.15); color: #9ca3af; }

.added-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--accent-cyan);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.skill-name {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-primary);
  font-family: 'Geist Mono', monospace;
}

.skill-source {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.72rem;
  color: var(--text-muted);
}

.skill-description {
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.5;
  flex: 1;
}

.skill-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}

.usage-count {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.72rem;
  color: var(--text-muted);
}

.skills-empty {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  color: var(--text-tertiary);
  font-size: 0.875rem;
}

/* Count badge */
.skill-count-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-muted);
}

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover { opacity: 0.85; }

.btn-scan {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  font-size: 0.78rem;
}

.btn-scan:hover:not(:disabled) {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.btn-scan:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-add {
  background: rgba(99, 179, 237, 0.1);
  color: var(--accent-cyan);
  border: 1px solid rgba(99, 179, 237, 0.25);
  font-size: 0.78rem;
  padding: 5px 11px;
}

.btn-add:hover {
  background: rgba(99, 179, 237, 0.2);
}

.btn-added {
  background: rgba(52, 211, 153, 0.1);
  color: #34d399;
  border: 1px solid rgba(52, 211, 153, 0.25);
  font-size: 0.78rem;
  padding: 5px 11px;
}

.btn-added:hover {
  background: rgba(52, 211, 153, 0.2);
}
</style>
