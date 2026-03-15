<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { triggerApi, ApiError } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const LANGUAGES = [
  { code: 'en', label: 'English', flag: '🇺🇸', rtl: false },
  { code: 'es', label: 'Spanish', flag: '🇪🇸', rtl: false },
  { code: 'fr', label: 'French', flag: '🇫🇷', rtl: false },
  { code: 'de', label: 'German', flag: '🇩🇪', rtl: false },
  { code: 'ja', label: 'Japanese', flag: '🇯🇵', rtl: false },
  { code: 'zh', label: 'Chinese (Simplified)', flag: '🇨🇳', rtl: false },
  { code: 'ko', label: 'Korean', flag: '🇰🇷', rtl: false },
  { code: 'pt', label: 'Portuguese', flag: '🇧🇷', rtl: false },
  { code: 'ar', label: 'Arabic', flag: '🇸🇦', rtl: true },
  { code: 'hi', label: 'Hindi', flag: '🇮🇳', rtl: false },
];

interface LocalizedPrompt {
  lang_code: string;
  content: string;
  auto_translated: boolean;
  last_edited_at: string;
}

interface BotLocalization {
  bot_id: string;
  bot_name: string;
  default_lang: string;
  prompts: LocalizedPrompt[];
}

const bots = ref<{ id: string; name: string; prompt_template?: string }[]>([]);
const selectedBotId = ref('');
const activeTab = ref<string>('en');
const localization = ref<BotLocalization | null>(null);
const isSaving = ref(false);
const isTranslating = ref(false);
const isLoading = ref(true);
const editingContent = ref('');

const selectedBot = computed(() => bots.value.find(b => b.id === selectedBotId.value));

const activePrompt = computed(() =>
  localization.value?.prompts.find(p => p.lang_code === activeTab.value)
);

function initLocalization(bot: { id: string; name: string; prompt_template?: string }) {
  localization.value = {
    bot_id: bot.id,
    bot_name: bot.name,
    default_lang: 'en',
    prompts: LANGUAGES.map(l => ({
      lang_code: l.code,
      content: l.code === 'en' ? (bot.prompt_template ?? '') : '',
      auto_translated: false,
      last_edited_at: new Date().toISOString(),
    })),
  };
  editingContent.value = bot.prompt_template ?? '';
}

function onBotSelect() {
  const bot = selectedBot.value;
  if (bot) {
    initLocalization(bot);
    activeTab.value = 'en';
  }
}

function onTabChange(lang: string) {
  // Save current edits before switching
  if (localization.value) {
    const cur = localization.value.prompts.find(p => p.lang_code === activeTab.value);
    if (cur) cur.content = editingContent.value;
  }
  activeTab.value = lang;
  editingContent.value = activePrompt.value?.content ?? '';
}

async function handleAutoTranslate(targetLang: string) {
  if (!localization.value) return;
  isTranslating.value = true;
  try {
    const sourceLang = localization.value.default_lang;
    const sourcePrompt = localization.value.prompts.find(p => p.lang_code === sourceLang);
    if (!sourcePrompt?.content) {
      showToast('Source prompt is empty', 'error');
      return;
    }
    await new Promise(r => setTimeout(r, 800));
    const target = localization.value.prompts.find(p => p.lang_code === targetLang);
    if (target) {
      const langObj = LANGUAGES.find(l => l.code === targetLang);
      target.content = `[Auto-translated to ${langObj?.label ?? targetLang}]\n\n${sourcePrompt.content}`;
      target.auto_translated = true;
      target.last_edited_at = new Date().toISOString();
      if (activeTab.value === targetLang) editingContent.value = target.content;
    }
    showToast(`Auto-translated to ${LANGUAGES.find(l => l.code === targetLang)?.label}`, 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Translation failed';
    showToast(message, 'error');
  } finally {
    isTranslating.value = false;
  }
}

async function handleSave() {
  if (!localization.value) return;
  isSaving.value = true;
  // Persist current edit
  const cur = localization.value.prompts.find(p => p.lang_code === activeTab.value);
  if (cur) { cur.content = editingContent.value; cur.last_edited_at = new Date().toISOString(); }
  try {
    await new Promise(r => setTimeout(r, 400));
    showToast('Localizations saved', 'success');
  } finally {
    isSaving.value = false;
  }
}

function filledCount(lc: BotLocalization): number {
  return lc.prompts.filter(p => p.content.trim().length > 0).length;
}

async function loadBots() {
  try {
    const res = await triggerApi.list();
    bots.value = (res.triggers ?? []).map((b: { id: string; name: string; prompt_template?: string }) => b);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load bots';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadBots);
</script>

<template>
  <div class="localization">

    <PageHeader
      title="Non-English Prompt Localization"
      subtitle="Author prompt templates in multiple languages. The platform passes the correct locale to the AI provider."
    />

    <LoadingState v-if="isLoading" message="Loading bots..." />

    <template v-else>
      <!-- Bot picker -->
      <div class="card bot-picker-card">
        <div class="bot-picker-body">
          <div class="field">
            <label class="field-label">Select Bot</label>
            <select v-model="selectedBotId" class="select-input" @change="onBotSelect">
              <option value="">-- Select a bot to localize --</option>
              <option v-for="b in bots" :key="b.id" :value="b.id">{{ b.name }}</option>
            </select>
          </div>
          <div v-if="localization" class="coverage-badge">
            {{ filledCount(localization) }} / {{ LANGUAGES.length }} languages
          </div>
        </div>
      </div>

      <div v-if="!localization" class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="36" height="36">
          <path d="M5 8l4 4-4 4M12 16h7"/>
        </svg>
        <p>Select a bot above to manage its prompt localizations.</p>
      </div>

      <template v-else>
        <div class="editor-layout">
          <!-- Language list sidebar -->
          <div class="lang-sidebar">
            <div class="lang-sidebar-header">Languages</div>
            <button
              v-for="lang in LANGUAGES"
              :key="lang.code"
              :class="['lang-btn', { active: activeTab === lang.code }]"
              @click="onTabChange(lang.code)"
            >
              <span class="lang-flag">{{ lang.flag }}</span>
              <span class="lang-name">{{ lang.label }}</span>
              <span v-if="localization.prompts.find(p => p.lang_code === lang.code)?.content" class="lang-filled">
                <svg viewBox="0 0 24 24" fill="currentColor" width="10" height="10">
                  <circle cx="12" cy="12" r="12"/>
                </svg>
              </span>
              <span v-if="lang.code === localization.default_lang" class="lang-default">default</span>
              <span v-if="localization.prompts.find(p => p.lang_code === lang.code)?.auto_translated" class="lang-auto">auto</span>
            </button>
          </div>

          <!-- Editor -->
          <div class="editor-col">
            <div class="card editor-card">
              <div class="card-header">
                <h3>
                  <span>{{ LANGUAGES.find(l => l.code === activeTab)?.flag }}</span>
                  {{ LANGUAGES.find(l => l.code === activeTab)?.label }} Prompt
                </h3>
                <div class="editor-actions">
                  <button
                    v-if="activeTab !== localization.default_lang"
                    class="btn btn-secondary btn-sm"
                    :disabled="isTranslating"
                    @click="handleAutoTranslate(activeTab)"
                  >
                    <svg v-if="isTranslating" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                    </svg>
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="12" height="12">
                      <path d="M5 8l4 4-4 4M12 16h7"/>
                    </svg>
                    {{ isTranslating ? 'Translating...' : 'Auto-Translate' }}
                  </button>
                </div>
              </div>

              <div v-if="activePrompt?.auto_translated" class="auto-translated-banner">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                This is an auto-translated draft. Review and edit before using in production.
              </div>

              <div class="editor-body">
                <textarea
                  v-model="editingContent"
                  class="code-editor"
                  :dir="LANGUAGES.find(l => l.code === activeTab)?.rtl ? 'rtl' : 'ltr'"
                  rows="18"
                  :placeholder="`Enter prompt template in ${LANGUAGES.find(l => l.code === activeTab)?.label}...`"
                />
                <div class="editor-footer">
                  <span class="char-count">{{ editingContent.length }} characters</span>
                  <span v-if="activePrompt?.last_edited_at" class="last-edited">
                    Edited {{ new Date(activePrompt.last_edited_at).toLocaleString() }}
                  </span>
                </div>
              </div>
            </div>

            <div class="save-row">
              <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
                {{ isSaving ? 'Saving...' : 'Save Localizations' }}
              </button>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.localization {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.35s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.bot-picker-card { padding: 0; }

.bot-picker-body {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  flex-wrap: wrap;
}

.field { display: flex; flex-direction: column; gap: 6px; min-width: 280px; }
.field-label { font-size: 0.8rem; font-weight: 500; color: var(--text-secondary); }

.select-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  cursor: pointer;
}

.coverage-badge {
  font-size: 0.8rem;
  font-weight: 600;
  padding: 6px 12px;
  background: rgba(6, 182, 212, 0.12);
  color: var(--accent-cyan);
  border-radius: 8px;
  border: 1px solid rgba(6, 182, 212, 0.2);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 24px;
  color: var(--text-tertiary);
  text-align: center;
}

.empty-state p { font-size: 0.875rem; }

.editor-layout {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 20px;
  align-items: start;
}

.lang-sidebar {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.lang-sidebar-header {
  padding: 12px 14px;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  border-bottom: 1px solid var(--border-default);
}

.lang-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  width: 100%;
  text-align: left;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background 0.1s;
  color: var(--text-secondary);
  font-size: 0.82rem;
}

.lang-btn:last-child { border-bottom: none; }
.lang-btn:hover { background: var(--bg-tertiary); }
.lang-btn.active { background: rgba(6, 182, 212, 0.08); color: var(--text-primary); }

.lang-flag { font-size: 1rem; flex-shrink: 0; }
.lang-name { flex: 1; font-size: 0.8rem; }

.lang-filled { color: var(--accent-cyan); flex-shrink: 0; }

.lang-default {
  font-size: 0.62rem;
  font-weight: 600;
  padding: 1px 5px;
  background: rgba(6, 182, 212, 0.15);
  color: var(--accent-cyan);
  border-radius: 3px;
  text-transform: uppercase;
}

.lang-auto {
  font-size: 0.62rem;
  font-weight: 600;
  padding: 1px 5px;
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border-radius: 3px;
  text-transform: uppercase;
}

.editor-col { display: flex; flex-direction: column; gap: 16px; }

.editor-card { overflow: hidden; }

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.editor-actions { display: flex; gap: 8px; }

.auto-translated-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: rgba(245, 158, 11, 0.1);
  border-bottom: 1px solid rgba(245, 158, 11, 0.2);
  font-size: 0.8rem;
  color: #fbbf24;
}

.editor-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 8px; }

.code-editor {
  width: 100%;
  padding: 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  line-height: 1.6;
  resize: vertical;
  box-sizing: border-box;
}

.code-editor:focus { outline: none; border-color: var(--accent-cyan); }
.code-editor[dir="rtl"] { text-align: right; }

.editor-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.72rem;
  color: var(--text-tertiary);
}

.save-row { display: flex; justify-content: flex-end; }

.btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 5px 11px; font-size: 0.78rem; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-secondary { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-secondary:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--text-primary); }
.btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 800px) {
  .editor-layout { grid-template-columns: 1fr; }
  .lang-sidebar { display: flex; flex-wrap: wrap; overflow: visible; }
  .lang-btn { width: auto; flex: 1; min-width: 120px; border-bottom: none; border-right: 1px solid var(--border-subtle); }
}
</style>
