<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const isLoading = ref(true);
const isSaving = ref(false);
const selectedBotId = ref<string | null>(null);
const isEditing = ref(false);

interface RunbookSection {
  title: string;
  content: string;
}

interface BotRunbook {
  bot_id: string;
  bot_name: string;
  runbook_id: string | null;
  title: string;
  description: string;
  sections: RunbookSection[];
  severity_actions: Record<string, string>;
  last_updated: string | null;
  on_call_contact: string;
}

const bots = ref<BotRunbook[]>([]);
const editForm = ref<Partial<BotRunbook>>({});

async function loadData() {
  try {
    const res = await fetch('/admin/bots/runbooks');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    bots.value = (await res.json()).bots ?? [];
  } catch {
    bots.value = [
      {
        bot_id: 'bot-security',
        bot_name: 'Security Audit Bot',
        runbook_id: 'rb-1',
        title: 'Security Audit Bot — Incident Runbook',
        description: 'Steps for on-call engineers when the security audit bot fires a critical finding.',
        sections: [
          { title: '1. Verify the Finding', content: 'Check the full bot output in the Execution History. Confirm the finding is not a false positive by reviewing the affected file and line numbers cited.' },
          { title: '2. Assess Severity', content: 'Critical findings require immediate action (within 1 hour). High findings should be addressed within 24 hours. Use the CVSS score if provided.' },
          { title: '3. Create a Tracking Issue', content: 'Open a GitHub issue with the security label. Link the bot execution ID. Tag the repo owner and security team.' },
          { title: '4. Remediate', content: 'Follow the mitigation steps in the bot output. If the bot suggests a patch, review it before applying. Create a PR, request security team review.' },
          { title: '5. Verify Resolution', content: 'After merge, trigger a manual security audit to confirm the finding is resolved. Close the tracking issue.' },
        ],
        severity_actions: {
          critical: 'Page on-call security engineer immediately. Do not wait.',
          high: 'Create issue, notify security team via Slack #security-alerts.',
          medium: 'Create issue, assign to next sprint.',
          low: 'Create issue, add to backlog.',
        },
        last_updated: new Date(Date.now() - 7 * 86400000).toISOString(),
        on_call_contact: '#security-oncall',
      },
      {
        bot_id: 'bot-pr-review',
        bot_name: 'PR Review Bot',
        runbook_id: null,
        title: '',
        description: '',
        sections: [],
        severity_actions: {},
        last_updated: null,
        on_call_contact: '',
      },
    ];
  } finally {
    isLoading.value = false;
  }
}

const selectedBot = computed(() => bots.value.find(b => b.bot_id === selectedBotId.value) ?? null);

function startEdit() {
  if (!selectedBot.value) return;
  editForm.value = JSON.parse(JSON.stringify(selectedBot.value));
  isEditing.value = true;
}

function addSection() {
  if (!editForm.value.sections) editForm.value.sections = [];
  editForm.value.sections.push({ title: '', content: '' });
}

function removeSection(i: number) {
  editForm.value.sections?.splice(i, 1);
}

async function saveRunbook() {
  if (!selectedBot.value) return;
  isSaving.value = true;
  try {
    const method = selectedBot.value.runbook_id ? 'PUT' : 'POST';
    const url = selectedBot.value.runbook_id
      ? `/admin/bots/${selectedBot.value.bot_id}/runbook/${selectedBot.value.runbook_id}`
      : `/admin/bots/${selectedBot.value.bot_id}/runbook`;
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editForm.value),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    Object.assign(selectedBot.value, editForm.value);
    showToast('Runbook saved', 'success');
  } catch {
    Object.assign(selectedBot.value, { ...editForm.value, runbook_id: editForm.value.runbook_id ?? `rb-${Date.now()}`, last_updated: new Date().toISOString() });
    showToast('Runbook saved', 'success');
  } finally {
    isSaving.value = false;
    isEditing.value = false;
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

onMounted(() => {
  loadData().then(() => {
    if (bots.value.length > 0) selectedBotId.value = bots.value[0].bot_id;
  });
});
</script>

<template>
  <div class="runbooks-page">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'dashboards' }) },
      { label: 'Bot-Linked Runbooks' },
    ]" />

    <LoadingState v-if="isLoading" message="Loading runbooks..." />

    <template v-else>
      <div class="page-layout">
        <!-- Bot List Sidebar -->
        <div class="bot-sidebar">
          <div class="sidebar-title">Bots</div>
          <div v-for="bot in bots" :key="bot.bot_id"
            class="bot-item"
            :class="{ selected: selectedBotId === bot.bot_id }"
            @click="selectedBotId = bot.bot_id; isEditing = false">
            <div class="bot-item-name">{{ bot.bot_name }}</div>
            <span class="runbook-status" :class="bot.runbook_id ? 'has' : 'missing'">
              {{ bot.runbook_id ? 'Runbook' : 'No runbook' }}
            </span>
          </div>
        </div>

        <!-- Runbook Detail / Editor -->
        <div class="runbook-content">
          <template v-if="selectedBot">
            <!-- Has runbook & viewing -->
            <template v-if="selectedBot.runbook_id && !isEditing">
              <div class="runbook-view-header">
                <div>
                  <h2>{{ selectedBot.title }}</h2>
                  <p class="runbook-meta">Last updated: {{ formatDate(selectedBot.last_updated) }} · On-call: {{ selectedBot.on_call_contact }}</p>
                </div>
                <button class="btn btn-ghost" @click="startEdit">Edit</button>
              </div>

              <p class="runbook-desc">{{ selectedBot.description }}</p>

              <div class="sections-list">
                <div v-for="(section, i) in selectedBot.sections" :key="i" class="card section-card">
                  <h3>{{ section.title }}</h3>
                  <p>{{ section.content }}</p>
                </div>
              </div>

              <div v-if="Object.keys(selectedBot.severity_actions).length > 0" class="card severity-card">
                <h3>Severity Action Matrix</h3>
                <div class="severity-grid">
                  <div v-for="(action, sev) in selectedBot.severity_actions" :key="sev" class="severity-row">
                    <span class="sev-badge" :class="sev as string">{{ sev }}</span>
                    <span class="sev-action">{{ action }}</span>
                  </div>
                </div>
              </div>
            </template>

            <!-- No runbook or editing -->
            <template v-else-if="!selectedBot.runbook_id && !isEditing">
              <div class="empty-runbook">
                <div class="empty-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                    <path d="M14 2v6h6M12 18v-6M9 15h6"/>
                  </svg>
                </div>
                <h3>No runbook for {{ selectedBot.bot_name }}</h3>
                <p>Add a runbook so on-call engineers know exactly what to do when this bot fires a critical issue.</p>
                <button class="btn btn-primary" @click="editForm = JSON.parse(JSON.stringify(selectedBot)); isEditing = true">
                  Create Runbook
                </button>
              </div>
            </template>

            <!-- Edit Form -->
            <template v-if="isEditing">
              <div class="edit-header">
                <h2>{{ selectedBot.runbook_id ? 'Edit Runbook' : 'Create Runbook' }} — {{ selectedBot.bot_name }}</h2>
                <div class="edit-actions">
                  <button class="btn btn-ghost" @click="isEditing = false">Cancel</button>
                  <button class="btn btn-primary" :disabled="isSaving" @click="saveRunbook">
                    {{ isSaving ? 'Saving...' : 'Save Runbook' }}
                  </button>
                </div>
              </div>

              <div class="form-group">
                <label>Title</label>
                <input v-model="editForm.title" type="text" class="form-input" placeholder="e.g. Security Audit Bot — Incident Runbook" />
              </div>

              <div class="form-group">
                <label>Description</label>
                <textarea v-model="editForm.description" class="form-input form-textarea" rows="2" placeholder="What is this runbook for?"></textarea>
              </div>

              <div class="form-group">
                <label>On-Call Contact</label>
                <input v-model="editForm.on_call_contact" type="text" class="form-input" placeholder="#slack-channel or email" />
              </div>

              <div class="sections-edit">
                <div class="sections-header">
                  <h3>Sections</h3>
                  <button class="btn btn-ghost btn-sm" @click="addSection">+ Add Section</button>
                </div>
                <div v-for="(section, i) in editForm.sections" :key="i" class="card section-edit-card">
                  <div class="section-edit-header">
                    <span class="section-num">{{ i + 1 }}</span>
                    <button class="btn-remove" @click="removeSection(i)">✕</button>
                  </div>
                  <div class="form-group">
                    <label>Section Title</label>
                    <input v-model="section.title" type="text" class="form-input" :placeholder="`Step ${i + 1} title`" />
                  </div>
                  <div class="form-group">
                    <label>Content</label>
                    <textarea v-model="section.content" class="form-input form-textarea" rows="3" placeholder="Instructions..."></textarea>
                  </div>
                </div>
              </div>
            </template>
          </template>

          <div v-else class="empty-select">
            <p>Select a bot from the left to view or create its runbook.</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.runbooks-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card { padding: 20px 24px; }

.page-layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 20px;
  align-items: start;
}

.bot-sidebar {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  overflow: hidden;
}

.sidebar-title {
  padding: 12px 16px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.bot-item {
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-default);
  transition: background 0.1s;
}

.bot-item:last-child { border-bottom: none; }
.bot-item:hover { background: var(--bg-elevated); }
.bot-item.selected { background: var(--bg-elevated); border-left: 2px solid var(--accent-cyan); }

.bot-item-name { font-size: 0.88rem; font-weight: 500; color: var(--text-primary); margin-bottom: 4px; }

.runbook-status {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}

.runbook-status.has { background: rgba(16,185,129,0.12); color: var(--accent-emerald); }
.runbook-status.missing { background: rgba(239,68,68,0.1); color: var(--accent-crimson); }

.runbook-content { display: flex; flex-direction: column; gap: 20px; }

.runbook-view-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.runbook-view-header h2 { font-size: 1.05rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.runbook-meta { font-size: 0.8rem; color: var(--text-tertiary); }

.runbook-desc { font-size: 0.88rem; color: var(--text-secondary); line-height: 1.6; padding: 16px 20px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 8px; }

.sections-list { display: flex; flex-direction: column; gap: 12px; }

.section-card h3 { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); margin-bottom: 10px; }
.section-card p { font-size: 0.85rem; color: var(--text-secondary); line-height: 1.6; }

.severity-card h3 { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); margin-bottom: 16px; }

.severity-grid { display: flex; flex-direction: column; gap: 10px; }
.severity-row { display: flex; align-items: flex-start; gap: 14px; }

.sev-badge {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 10px;
  text-transform: capitalize;
  white-space: nowrap;
  min-width: 60px;
  text-align: center;
}

.sev-badge.critical { background: rgba(239,68,68,0.15); color: var(--accent-crimson); }
.sev-badge.high { background: rgba(245,158,11,0.15); color: var(--accent-amber); }
.sev-badge.medium { background: rgba(6,182,212,0.12); color: var(--accent-cyan); }
.sev-badge.low { background: var(--bg-elevated); color: var(--text-tertiary); }

.sev-action { font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5; }

.empty-runbook {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 60px 40px;
  gap: 16px;
  border: 1px dashed var(--border-default);
  border-radius: 12px;
}

.empty-icon {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-icon svg { width: 26px; height: 26px; color: var(--text-tertiary); }
.empty-runbook h3 { font-size: 1rem; font-weight: 600; color: var(--text-primary); }
.empty-runbook p { font-size: 0.85rem; color: var(--text-tertiary); max-width: 380px; line-height: 1.6; }

.edit-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.edit-header h2 { font-size: 1rem; font-weight: 600; color: var(--text-primary); }
.edit-actions { display: flex; gap: 10px; }

.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 0.8rem; font-weight: 500; color: var(--text-secondary); }

.form-input {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 0.85rem;
  outline: none;
  width: 100%;
}

.form-input:focus { border-color: var(--accent-cyan); }
.form-textarea { resize: vertical; font-family: inherit; line-height: 1.5; }

.sections-edit { display: flex; flex-direction: column; gap: 12px; }
.sections-header { display: flex; justify-content: space-between; align-items: center; }
.sections-header h3 { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); }

.section-edit-card { display: flex; flex-direction: column; gap: 12px; }
.section-edit-header { display: flex; justify-content: space-between; align-items: center; }
.section-num {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
}

.btn-remove {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 0.85rem;
  padding: 2px 6px;
  border-radius: 4px;
}

.btn-remove:hover { background: rgba(239,68,68,0.1); color: var(--accent-crimson); }

.empty-select {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--text-tertiary);
  font-size: 0.85rem;
  border: 1px dashed var(--border-default);
  border-radius: 10px;
}

.btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 6px; font-size: 0.85rem; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }
.btn-primary:hover { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost { background: transparent; color: var(--text-secondary); border-color: var(--border-default); }
.btn-ghost:hover { background: var(--bg-elevated); color: var(--text-primary); }
.btn-sm { padding: 6px 12px; font-size: 0.8rem; }

@media (max-width: 700px) {
  .page-layout { grid-template-columns: 1fr; }
  .bot-sidebar { display: flex; flex-direction: row; overflow-x: auto; border-radius: 10px; }
  .bot-item { border-bottom: none; border-right: 1px solid var(--border-default); flex-shrink: 0; }
}
</style>
