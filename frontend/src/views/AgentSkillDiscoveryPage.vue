<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';

const router = useRouter();

interface DiscoverySource {
  id: string;
  name: string;
  type: 'repository' | 'registry';
  url: string;
  lastScanned: string;
  skillCount: number;
  status: 'active' | 'scanning' | 'error';
}

interface DiscoveredSkill {
  id: string;
  name: string;
  category: 'git' | 'code-review' | 'security' | 'testing' | 'deployment';
  source: string;
  description: string;
  usageCount: number;
  addedToPrompt: boolean;
}

interface Recommendation {
  id: string;
  skillName: string;
  category: 'git' | 'code-review' | 'security' | 'testing' | 'deployment';
  reason: string;
  matchScore: number;
}

const sources = ref<DiscoverySource[]>([
  {
    id: 'src-1',
    name: 'agented/core',
    type: 'repository',
    url: 'github.com/agented/core',
    lastScanned: '3 minutes ago',
    skillCount: 18,
    status: 'active',
  },
  {
    id: 'src-2',
    name: 'Plugin Registry (Official)',
    type: 'registry',
    url: 'registry.agented.dev/official',
    lastScanned: '27 minutes ago',
    skillCount: 42,
    status: 'active',
  },
  {
    id: 'src-3',
    name: 'myorg/devtools',
    type: 'repository',
    url: 'github.com/myorg/devtools',
    lastScanned: '2 hours ago',
    skillCount: 7,
    status: 'error',
  },
]);

const skills = ref<DiscoveredSkill[]>([
  {
    id: 'sk-1',
    name: 'git-diff-summarizer',
    category: 'git',
    source: 'agented/core',
    description: 'Summarizes git diffs into human-readable change descriptions with scope and impact analysis.',
    usageCount: 134,
    addedToPrompt: false,
  },
  {
    id: 'sk-2',
    name: 'pr-review-checklist',
    category: 'code-review',
    source: 'Plugin Registry (Official)',
    description: 'Runs a structured checklist against open pull requests and posts inline review comments.',
    usageCount: 89,
    addedToPrompt: true,
  },
  {
    id: 'sk-3',
    name: 'secret-scanner',
    category: 'security',
    source: 'Plugin Registry (Official)',
    description: 'Scans repository files for accidentally committed secrets, API keys, and credentials.',
    usageCount: 211,
    addedToPrompt: false,
  },
  {
    id: 'sk-4',
    name: 'test-coverage-reporter',
    category: 'testing',
    source: 'agented/core',
    description: 'Parses test coverage output and generates a summary with uncovered lines highlighted.',
    usageCount: 67,
    addedToPrompt: false,
  },
  {
    id: 'sk-5',
    name: 'deploy-health-check',
    category: 'deployment',
    source: 'Plugin Registry (Official)',
    description: 'Validates deployment health by probing endpoints and comparing response fingerprints.',
    usageCount: 45,
    addedToPrompt: false,
  },
  {
    id: 'sk-6',
    name: 'branch-naming-enforcer',
    category: 'git',
    source: 'myorg/devtools',
    description: 'Enforces branch naming conventions and suggests corrections for non-compliant branch names.',
    usageCount: 22,
    addedToPrompt: false,
  },
]);

const recommendations = ref<Recommendation[]>([
  {
    id: 'rec-1',
    skillName: 'secret-scanner',
    category: 'security',
    reason: 'Your bot-security agent runs weekly audits — this skill will enhance coverage for committed secrets.',
    matchScore: 97,
  },
  {
    id: 'rec-2',
    skillName: 'pr-review-checklist',
    category: 'code-review',
    reason: 'bot-pr-review triggers on pull_request events and this skill aligns directly with its workflow.',
    matchScore: 93,
  },
  {
    id: 'rec-3',
    skillName: 'test-coverage-reporter',
    category: 'testing',
    reason: 'Multiple agents in your workspace run after CI pipelines — coverage reporting adds immediate value.',
    matchScore: 81,
  },
]);

const searchQuery = ref('');
const selectedCategory = ref<'all' | 'git' | 'code-review' | 'security' | 'testing' | 'deployment'>('all');
const scanningId = ref<string | null>(null);

const filteredSkills = computed(() => {
  return skills.value.filter(skill => {
    const matchesCategory = selectedCategory.value === 'all' || skill.category === selectedCategory.value;
    const matchesSearch =
      searchQuery.value.trim() === '' ||
      skill.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      skill.description.toLowerCase().includes(searchQuery.value.toLowerCase());
    return matchesCategory && matchesSearch;
  });
});

const categoryLabel: Record<DiscoveredSkill['category'], string> = {
  git: 'Git',
  'code-review': 'Code Review',
  security: 'Security',
  testing: 'Testing',
  deployment: 'Deployment',
};

async function scanSource(source: DiscoverySource) {
  if (scanningId.value) return;
  scanningId.value = source.id;
  source.status = 'scanning';
  await new Promise(resolve => setTimeout(resolve, 1800));
  source.status = 'active';
  source.lastScanned = 'just now';
  scanningId.value = null;
}

function toggleAddToPrompt(skill: DiscoveredSkill) {
  skill.addedToPrompt = !skill.addedToPrompt;
}

function addRecommendation(rec: Recommendation) {
  const skill = skills.value.find(s => s.name === rec.skillName);
  if (skill) {
    skill.addedToPrompt = true;
  }
}
</script>

<template>
  <div class="skill-discovery">
    <AppBreadcrumb :items="[
      { label: 'Agents', action: () => router.push({ name: 'agents' }) },
      { label: 'Skill Discovery' },
    ]" />

    <PageHeader
      title="Skill Auto-Discovery"
      subtitle="Automatically detect and index skills from connected repositories and plugin registries."
    />

    <!-- Discovery Sources -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          Discovery Sources
        </h3>
        <button class="btn btn-primary">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <line x1="12" y1="5" x2="12" y2="19"/>
            <line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Add Source
        </button>
      </div>
      <div class="sources-list">
        <div v-for="source in sources" :key="source.id" class="source-row">
          <div class="source-icon">
            <svg v-if="source.type === 'repository'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
              <line x1="8" y1="21" x2="16" y2="21"/>
              <line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
          </div>
          <div class="source-info">
            <span class="source-name">{{ source.name }}</span>
            <span class="source-url">{{ source.url }}</span>
          </div>
          <div class="source-meta">
            <span class="source-stat">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
              </svg>
              {{ source.skillCount }} skills
            </span>
            <span class="source-scanned">Last scanned {{ source.lastScanned }}</span>
          </div>
          <div class="source-status">
            <span :class="['status-badge', source.status]">
              <span v-if="source.status === 'scanning'" class="pulse-dot"></span>
              {{ source.status === 'active' ? 'Active' : source.status === 'scanning' ? 'Scanning…' : 'Error' }}
            </span>
          </div>
          <button
            class="btn btn-scan"
            :disabled="scanningId !== null"
            @click="scanSource(source)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
              <polyline points="23 4 23 10 17 10"/>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
            Scan Now
          </button>
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
            placeholder="Search skills by name or description…"
          />
        </div>
        <select v-model="selectedCategory" class="category-select">
          <option value="all">All Categories</option>
          <option value="git">Git</option>
          <option value="code-review">Code Review</option>
          <option value="security">Security</option>
          <option value="testing">Testing</option>
          <option value="deployment">Deployment</option>
        </select>
      </div>

      <!-- Skills Grid -->
      <div class="skills-grid">
        <div
          v-for="skill in filteredSkills"
          :key="skill.id"
          class="skill-card"
          :class="{ 'is-added': skill.addedToPrompt }"
        >
          <div class="skill-card-top">
            <span :class="['category-badge', skill.category]">{{ categoryLabel[skill.category] }}</span>
            <span v-if="skill.addedToPrompt" class="added-indicator">
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
            {{ skill.source }}
          </div>
          <div class="skill-description">{{ skill.description }}</div>
          <div class="skill-footer">
            <span class="usage-count">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
              </svg>
              {{ skill.usageCount }} uses
            </span>
            <button
              :class="['btn', skill.addedToPrompt ? 'btn-added' : 'btn-add']"
              @click="toggleAddToPrompt(skill)"
            >
              <svg v-if="!skill.addedToPrompt" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              {{ skill.addedToPrompt ? 'Remove' : 'Add to Prompt' }}
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

    <!-- Recommendations -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
          </svg>
          Recommended for Your Bots
        </h3>
        <span class="rec-label">AI-matched suggestions</span>
      </div>
      <div class="rec-list">
        <div v-for="rec in recommendations" :key="rec.id" class="rec-row">
          <div class="rec-score">
            <span class="score-value">{{ rec.matchScore }}%</span>
            <span class="score-label">match</span>
          </div>
          <div class="rec-info">
            <div class="rec-name">
              {{ rec.skillName }}
              <span :class="['category-badge', rec.category]">{{ categoryLabel[rec.category] }}</span>
            </div>
            <div class="rec-reason">{{ rec.reason }}</div>
          </div>
          <button
            :class="['btn', skills.find(s => s.name === rec.skillName)?.addedToPrompt ? 'btn-added' : 'btn-add']"
            @click="addRecommendation(rec)"
          >
            <svg v-if="!skills.find(s => s.name === rec.skillName)?.addedToPrompt" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="12" height="12">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            {{ skills.find(s => s.name === rec.skillName)?.addedToPrompt ? 'Added' : 'Add to Prompt' }}
          </button>
        </div>
      </div>
    </div>
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

/* Recommendations */
.rec-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-style: italic;
}

.rec-list {
  display: flex;
  flex-direction: column;
}

.rec-row {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}

.rec-row:hover { background: var(--bg-tertiary); }
.rec-row:last-child { border-bottom: none; }

.rec-score {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 48px;
}

.score-value {
  font-size: 1rem;
  font-weight: 700;
  color: var(--accent-cyan);
}

.score-label {
  font-size: 0.65rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.rec-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rec-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-primary);
  font-family: 'Geist Mono', monospace;
}

.rec-reason {
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.5;
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
