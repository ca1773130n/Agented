<script setup lang="ts">
import { ref, computed } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();

interface Skill {
  id: string;
  name: string;
  category: string;
  description: string;
  conflicts?: string[];
}

interface ComposerSlot {
  order: number;
  skillId: string;
}

const availableSkills: Skill[] = [
  { id: 'sk-safety', name: 'Safe Operations', category: 'safety', description: 'Prevents destructive file ops, validates commands before execution.' },
  { id: 'sk-review', name: 'Code Review', category: 'review', description: 'Structured PR review with categories: correctness, style, security.' },
  { id: 'sk-security', name: 'Security Analysis', category: 'security', description: 'OWASP top-10 scanning, dependency audit, secrets detection.', conflicts: ['sk-fast'] },
  { id: 'sk-test', name: 'Test Generation', category: 'testing', description: 'TDD-first approach: writes failing tests before implementation.' },
  { id: 'sk-docs', name: 'Documentation', category: 'docs', description: 'Generates JSDoc, OpenAPI annotations, and README updates.' },
  { id: 'sk-git', name: 'Git Workflow', category: 'vcs', description: 'Conventional commits, branch naming, PR best practices.' },
  { id: 'sk-fast', name: 'Fast Mode', category: 'performance', description: 'Skips exhaustive checks for speed; not for production PRs.', conflicts: ['sk-security'] },
  { id: 'sk-context', name: 'Context Awareness', category: 'context', description: 'Reads project README, CLAUDE.md, and recent git log before responding.' },
];

const categoryColors: Record<string, string> = {
  safety: '#34d399',
  review: '#06b6d4',
  security: '#f59e0b',
  testing: '#a78bfa',
  docs: '#60a5fa',
  vcs: '#94a3b8',
  performance: '#f97316',
  context: '#ec4899',
};

const composedSlots = ref<ComposerSlot[]>([
  { order: 0, skillId: 'sk-safety' },
  { order: 1, skillId: 'sk-review' },
]);

const composerName = ref('My PR Review Agent');

const composedSkills = computed(() =>
  composedSlots.value
    .slice()
    .sort((a, b) => a.order - b.order)
    .map(slot => availableSkills.find(s => s.id === slot.skillId)!)
    .filter(Boolean)
);

const conflictWarnings = computed(() => {
  const warnings: string[] = [];
  for (const skill of composedSkills.value) {
    if (skill.conflicts) {
      for (const conflictId of skill.conflicts) {
        if (composedSlots.value.some(s => s.skillId === conflictId)) {
          const conflictSkill = availableSkills.find(s => s.id === conflictId);
          warnings.push(`"${skill.name}" conflicts with "${conflictSkill?.name}"`);
        }
      }
    }
  }
  return [...new Set(warnings)];
});

const availableToAdd = computed(() =>
  availableSkills.filter(s => !composedSlots.value.some(slot => slot.skillId === s.id))
);

function addSkill(skill: Skill) {
  const maxOrder = composedSlots.value.reduce((max, s) => Math.max(max, s.order), -1);
  composedSlots.value.push({ order: maxOrder + 1, skillId: skill.id });
}

function removeSkill(skillId: string) {
  const idx = composedSlots.value.findIndex(s => s.skillId === skillId);
  if (idx !== -1) composedSlots.value.splice(idx, 1);
}

function moveUp(idx: number) {
  if (idx === 0) return;
  const sorted = composedSlots.value.slice().sort((a, b) => a.order - b.order);
  const temp = sorted[idx].order;
  sorted[idx].order = sorted[idx - 1].order;
  sorted[idx - 1].order = temp;
}

function moveDown(idx: number) {
  const sorted = composedSlots.value.slice().sort((a, b) => a.order - b.order);
  if (idx === sorted.length - 1) return;
  const temp = sorted[idx].order;
  sorted[idx].order = sorted[idx + 1].order;
  sorted[idx + 1].order = temp;
}

function saveComposition() {
  if (!composerName.value.trim()) {
    showToast('Please enter a skill set name', 'error');
    return;
  }
  showToast(`"${composerName.value}" saved with ${composedSkills.value.length} skills`, 'success');
}

function skillColor(skillId: string) {
  const cat = availableSkills.find(s => s.id === skillId)?.category ?? 'review';
  return categoryColors[cat] ?? '#94a3b8';
}
</script>

<template>
  <div class="skill-composer">
    <AppBreadcrumb :items="[{ label: 'Skills' }, { label: 'Visual Skill Composer' }]" />

    <PageHeader
      title="Visual Skill Composer"
      subtitle="Combine and order skills to build coherent agent personas with a visual composer."
    />

    <div class="composer-layout">
      <!-- Left: Available skills -->
      <div class="panel available-panel">
        <div class="panel-header">
          <h3>Available Skills</h3>
          <span class="count-badge">{{ availableToAdd.length }} remaining</span>
        </div>
        <div class="skills-library">
          <div
            v-for="skill in availableToAdd"
            :key="skill.id"
            class="skill-library-item"
            :style="{ borderLeftColor: categoryColors[skill.category] }"
            @click="addSkill(skill)"
          >
            <div class="skill-lib-top">
              <span class="skill-lib-name">{{ skill.name }}</span>
              <span class="skill-category-tag" :style="{ color: categoryColors[skill.category] }">
                {{ skill.category }}
              </span>
            </div>
            <p class="skill-lib-desc">{{ skill.description }}</p>
            <button class="add-skill-btn">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              Add
            </button>
          </div>
          <div v-if="availableToAdd.length === 0" class="all-added">
            All skills have been added to the composition.
          </div>
        </div>
      </div>

      <!-- Right: Composer -->
      <div class="panel composer-panel">
        <div class="panel-header">
          <div class="name-field">
            <input v-model="composerName" type="text" class="name-input" placeholder="Skill set name..." />
          </div>
          <button class="btn btn-primary" @click="saveComposition">Save Skill Set</button>
        </div>

        <div v-if="conflictWarnings.length > 0" class="conflict-banner">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          <div>
            <div v-for="w in conflictWarnings" :key="w" class="conflict-item">{{ w }}</div>
          </div>
        </div>

        <div class="composition-area">
          <div
            v-for="(skill, idx) in composedSkills"
            :key="skill.id"
            class="composed-skill"
            :style="{ borderColor: skillColor(skill.id) + '40' }"
          >
            <div class="order-badge" :style="{ background: skillColor(skill.id) }">{{ idx + 1 }}</div>
            <div class="composed-skill-body">
              <div class="composed-skill-top">
                <span class="composed-skill-name">{{ skill.name }}</span>
                <span class="skill-category-tag" :style="{ color: skillColor(skill.id) }">
                  {{ skill.category }}
                </span>
              </div>
              <p class="composed-skill-desc">{{ skill.description }}</p>
            </div>
            <div class="composed-skill-controls">
              <button class="ctrl-btn" :disabled="idx === 0" @click="moveUp(idx)" title="Move up">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><polyline points="18 15 12 9 6 15"/></svg>
              </button>
              <button class="ctrl-btn" :disabled="idx === composedSkills.length - 1" @click="moveDown(idx)" title="Move down">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><polyline points="6 9 12 15 18 9"/></svg>
              </button>
              <button class="ctrl-btn remove-btn" @click="removeSkill(skill.id)" title="Remove">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>

          <div v-if="composedSkills.length === 0" class="empty-composition">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32" style="color: var(--text-muted)"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
            <p>No skills added yet. Click skills on the left to add them.</p>
          </div>
        </div>

        <div class="prompt-preview">
          <div class="preview-label">Prompt injection preview</div>
          <pre class="preview-code"># Skills: {{ composerName || 'Unnamed Set' }}
{{ composedSkills.map((s, i) => `${i + 1}. [${s.name}]: ${s.description}`).join('\n') }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skill-composer {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.composer-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px;
  align-items: start;
}

.panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
  gap: 12px;
}

.panel-header h3 {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.count-badge {
  font-size: 0.72rem;
  padding: 2px 7px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-tertiary);
}

.skills-library {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 600px;
  overflow-y: auto;
}

.skill-library-item {
  padding: 12px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-left: 3px solid;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skill-library-item:hover {
  border-color: var(--accent-cyan);
  background: var(--bg-secondary);
}

.skill-lib-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.skill-lib-name {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
}

.skill-category-tag {
  font-size: 0.68rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.skill-lib-desc {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.45;
}

.add-skill-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.72rem;
  padding: 4px 8px;
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.2);
  border-radius: 4px;
  color: var(--accent-cyan);
  cursor: pointer;
  width: fit-content;
  transition: all 0.15s;
}

.add-skill-btn:hover { background: rgba(6, 182, 212, 0.2); }

.all-added {
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.8rem;
  padding: 20px;
}

.name-field { flex: 1; }

.name-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 7px;
  color: var(--text-primary);
  font-size: 0.875rem;
  box-sizing: border-box;
}

.name-input:focus { outline: none; border-color: var(--accent-cyan); }

.conflict-banner {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  background: rgba(245, 158, 11, 0.08);
  border-bottom: 1px solid rgba(245, 158, 11, 0.2);
  color: #f59e0b;
  font-size: 0.8rem;
}

.conflict-banner svg { flex-shrink: 0; margin-top: 1px; }
.conflict-item { margin-bottom: 2px; }

.composition-area {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 200px;
}

.composed-skill {
  display: flex;
  align-items: stretch;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg-tertiary);
  border: 1px solid;
  border-radius: 8px;
}

.order-badge {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 700;
  color: #000;
  flex-shrink: 0;
  margin-top: 2px;
}

.composed-skill-body { flex: 1; display: flex; flex-direction: column; gap: 4px; }

.composed-skill-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.composed-skill-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.composed-skill-desc {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  margin: 0;
}

.composed-skill-controls {
  display: flex;
  flex-direction: column;
  gap: 4px;
  justify-content: center;
}

.ctrl-btn {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  border: 1px solid var(--border-default);
  background: var(--bg-secondary);
  color: var(--text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.ctrl-btn:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--text-primary); }
.ctrl-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.remove-btn:hover:not(:disabled) { border-color: #f87171; color: #f87171; }

.empty-composition {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 40px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.85rem;
}

.empty-composition p { margin: 0; }

.prompt-preview {
  border-top: 1px solid var(--border-default);
  padding: 16px 20px;
}

.preview-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.preview-code {
  font-size: 0.75rem;
  font-family: monospace;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 10px 14px;
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.5;
}

.btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 16px;
  border-radius: 7px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover { opacity: 0.85; }

@media (max-width: 900px) {
  .composer-layout { grid-template-columns: 1fr; }
}
</style>
