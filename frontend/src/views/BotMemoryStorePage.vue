<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { botMemoryApi } from '../services/api/bot-memory';
import type { BotMemorySummary } from '../services/api/bot-memory';

const showToast = useToast();

interface MemoryEntry {
  key: string;
  value: string;
  updated_at: string;
  expires_at: string | null;
  source: 'bot' | 'manual';
}

interface BotMemory {
  botId: string;
  botName: string;
  entries: MemoryEntry[];
  usedBytes: number;
  maxBytes: number;
}

const bots = ref<BotMemory[]>([]);
const selectedBotId = ref<string | null>(null);
const showAddModal = ref(false);
const newKey = ref('');
const newValue = ref('');
const newExpiry = ref('');
const editingEntry = ref<MemoryEntry | null>(null);
const searchQuery = ref('');

const selectedBot = computed(() => bots.value.find(b => b.botId === selectedBotId.value) ?? null);

const filteredEntries = computed(() => {
  if (!selectedBot.value) return [];
  const q = searchQuery.value.toLowerCase();
  if (!q) return selectedBot.value.entries;
  return selectedBot.value.entries.filter(e =>
    e.key.toLowerCase().includes(q) || e.value.toLowerCase().includes(q)
  );
});

const usagePercent = computed(() => {
  if (!selectedBot.value) return 0;
  return Math.round((selectedBot.value.usedBytes / selectedBot.value.maxBytes) * 100);
});

function formatBytes(b: number) {
  if (b < 1024) return `${b} B`;
  return `${(b / 1024).toFixed(1)} KB`;
}

async function loadBotList() {
  try {
    const res = await botMemoryApi.listAll();
    bots.value = res.bots.map((b: BotMemorySummary) => ({
      botId: b.bot_id,
      botName: b.bot_name,
      entries: [],
      usedBytes: b.used_bytes,
      maxBytes: 65536,
    }));
    if (bots.value.length > 0 && !selectedBotId.value) {
      selectedBotId.value = bots.value[0].botId;
      await loadBotMemory(bots.value[0].botId);
    }
  } catch {
    // No memory entries yet — leave list empty
  }
}

async function loadBotMemory(botId: string) {
  try {
    const res = await botMemoryApi.getBotMemory(botId);
    const bot = bots.value.find(b => b.botId === botId);
    if (bot) {
      bot.entries = res.entries.map(e => ({
        key: e.key,
        value: e.value,
        updated_at: e.updated_at,
        expires_at: e.expires_at,
        source: e.source as 'bot' | 'manual',
      }));
      bot.usedBytes = res.used_bytes;
      bot.maxBytes = res.max_bytes;
    }
  } catch {
    // ignore
  }
}

async function selectBot(botId: string) {
  selectedBotId.value = botId;
  await loadBotMemory(botId);
}

function openAddModal() {
  newKey.value = '';
  newValue.value = '';
  newExpiry.value = '';
  editingEntry.value = null;
  showAddModal.value = true;
}

function openEditModal(entry: MemoryEntry) {
  editingEntry.value = entry;
  newKey.value = entry.key;
  newValue.value = entry.value;
  newExpiry.value = entry.expires_at ?? '';
  showAddModal.value = true;
}

async function saveEntry() {
  if (!newKey.value.trim() || !newValue.value.trim()) {
    showToast('Key and value are required', 'error');
    return;
  }
  if (!selectedBot.value) return;

  try {
    await botMemoryApi.upsertEntry(selectedBot.value.botId, newKey.value.trim(), {
      value: newValue.value.trim(),
      expiresAt: newExpiry.value || null,
    });
    showToast(
      editingEntry.value
        ? `Memory key "${newKey.value}" updated`
        : `Memory key "${newKey.value}" added`,
      'success',
    );
    showAddModal.value = false;
    await loadBotMemory(selectedBot.value.botId);
  } catch {
    showToast('Failed to save memory entry', 'error');
  }
}

async function deleteEntry(key: string) {
  if (!selectedBot.value) return;
  try {
    await botMemoryApi.deleteEntry(selectedBot.value.botId, key);
    showToast(`Memory key "${key}" deleted`, 'success');
    await loadBotMemory(selectedBot.value.botId);
  } catch {
    showToast('Failed to delete memory entry', 'error');
  }
}

async function clearAllMemory() {
  if (!selectedBot.value) return;
  try {
    await botMemoryApi.clearAll(selectedBot.value.botId);
    showToast(`All memory cleared for ${selectedBot.value.botName}`, 'success');
    selectedBot.value.entries = [];
    selectedBot.value.usedBytes = 0;
  } catch {
    showToast('Failed to clear memory', 'error');
  }
}

onMounted(loadBotList);
</script>

<template>
  <div class="bot-memory">
    <AppBreadcrumb :items="[{ label: 'Bots' }, { label: 'Bot Memory Store' }]" />

    <PageHeader
      title="Per-Bot Persistent Memory"
      subtitle="Each bot maintains a key-value memory store across executions for learning and continuity."
    />

    <div class="memory-layout">
      <!-- Bot list sidebar -->
      <div class="bot-list-panel">
        <div class="panel-label">Select Bot</div>
        <div
          v-for="bot in bots"
          :key="bot.botId"
          class="bot-list-item"
          :class="{ selected: selectedBotId === bot.botId }"
          @click="selectBot(bot.botId)"
        >
          <div class="bot-list-name">{{ bot.botName }}</div>
          <div class="bot-list-meta">
            {{ bot.entries.length }} keys · {{ formatBytes(bot.usedBytes) }}
          </div>
        </div>
      </div>

      <!-- Memory editor -->
      <div class="memory-editor">
        <template v-if="selectedBot">
          <div class="editor-toolbar">
            <div class="usage-bar-wrap">
              <span class="usage-label">{{ formatBytes(selectedBot.usedBytes) }} / {{ formatBytes(selectedBot.maxBytes) }}</span>
              <div class="usage-bar">
                <div class="usage-fill" :style="{ width: `${usagePercent}%`, background: usagePercent > 80 ? '#f87171' : 'var(--accent-cyan)' }"></div>
              </div>
              <span class="usage-pct">{{ usagePercent }}%</span>
            </div>
            <input v-model="searchQuery" type="text" class="search-input" placeholder="Search keys..." />
            <button class="btn btn-secondary" @click="clearAllMemory">Clear All</button>
            <button class="btn btn-primary" @click="openAddModal">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              Add Key
            </button>
          </div>

          <div class="entries-table">
            <div class="table-header">
              <span>Key</span>
              <span>Value</span>
              <span>Source</span>
              <span>Updated</span>
              <span>Expires</span>
              <span></span>
            </div>
            <div v-for="entry in filteredEntries" :key="entry.key" class="table-row">
              <code class="entry-key">{{ entry.key }}</code>
              <div class="entry-value">
                <code>{{ entry.value.length > 60 ? entry.value.slice(0, 60) + '…' : entry.value }}</code>
              </div>
              <span class="source-badge" :class="entry.source">{{ entry.source }}</span>
              <span class="entry-meta">{{ entry.updated_at }}</span>
              <span class="entry-meta">{{ entry.expires_at ?? '—' }}</span>
              <div class="entry-actions">
                <button class="icon-btn" @click="openEditModal(entry)" title="Edit">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button class="icon-btn" @click="deleteEntry(entry.key)" title="Delete">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                </button>
              </div>
            </div>
            <div v-if="filteredEntries.length === 0" class="empty-entries">
              <p>No memory entries found.</p>
            </div>
          </div>
        </template>

        <div v-else class="no-selection">Select a bot to view its memory.</div>
      </div>
    </div>

    <!-- Add/Edit Modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>{{ editingEntry ? 'Edit Memory Key' : 'Add Memory Key' }}</h3>
          <button class="icon-btn" @click="showAddModal = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="field-group">
            <label class="field-label">Key</label>
            <input v-model="newKey" type="text" class="text-input" :disabled="!!editingEntry" placeholder="e.g. last_reviewed_prs" />
          </div>
          <div class="field-group">
            <label class="field-label">Value (JSON or string)</label>
            <textarea v-model="newValue" class="textarea-input" rows="4" placeholder='e.g. ["#142","#139"]'></textarea>
          </div>
          <div class="field-group">
            <label class="field-label">Expiry Date (optional)</label>
            <input v-model="newExpiry" type="date" class="text-input" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showAddModal = false">Cancel</button>
          <button class="btn btn-primary" @click="saveEntry">{{ editingEntry ? 'Update' : 'Add' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bot-memory {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.memory-layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 20px;
  align-items: start;
}

.bot-list-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.panel-label {
  padding: 12px 16px;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-default);
}

.bot-list-item {
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}

.bot-list-item:last-child { border-bottom: none; }
.bot-list-item:hover { background: var(--bg-tertiary); }
.bot-list-item.selected { background: rgba(6, 182, 212, 0.08); border-left: 2px solid var(--accent-cyan); }

.bot-list-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.bot-list-meta {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.memory-editor {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-default);
  flex-wrap: wrap;
}

.usage-bar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.usage-label {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.usage-bar {
  width: 80px;
  height: 5px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  overflow: hidden;
}

.usage-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s;
}

.usage-pct {
  font-size: 0.72rem;
  color: var(--text-tertiary);
}

.search-input {
  flex: 1;
  min-width: 120px;
  padding: 7px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 7px;
  color: var(--text-primary);
  font-size: 0.85rem;
}

.search-input:focus { outline: none; border-color: var(--accent-cyan); }

.entries-table { display: flex; flex-direction: column; }

.table-header {
  display: grid;
  grid-template-columns: 1.5fr 2fr 0.7fr 0.8fr 0.8fr 60px;
  gap: 12px;
  padding: 10px 20px;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.table-row {
  display: grid;
  grid-template-columns: 1.5fr 2fr 0.7fr 0.8fr 0.8fr 60px;
  gap: 12px;
  padding: 11px 20px;
  align-items: center;
  border-bottom: 1px solid var(--border-subtle);
}

.table-row:last-child { border-bottom: none; }
.table-row:hover { background: var(--bg-tertiary); }

.entry-key {
  font-family: monospace;
  font-size: 0.8rem;
  color: var(--accent-cyan);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entry-value code {
  font-family: monospace;
  font-size: 0.75rem;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
}

.source-badge {
  font-size: 0.68rem;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 500;
  width: fit-content;
}

.source-badge.bot {
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.2);
  color: var(--accent-cyan);
}

.source-badge.manual {
  background: rgba(167, 139, 250, 0.1);
  border: 1px solid rgba(167, 139, 250, 0.2);
  color: #a78bfa;
}

.entry-meta {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.entry-actions { display: flex; gap: 4px; }

.empty-entries {
  padding: 40px;
  text-align: center;
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.empty-entries p { margin: 0; }

.no-selection {
  padding: 60px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

.btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover { opacity: 0.85; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); }

.icon-btn {
  width: 26px;
  height: 26px;
  border-radius: 5px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.icon-btn:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  width: 480px;
  max-width: 95vw;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.modal-header h3 { font-size: 1rem; font-weight: 600; color: var(--text-primary); margin: 0; }

.modal-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-default);
}

.field-group { display: flex; flex-direction: column; gap: 6px; }

.field-label { font-size: 0.8rem; font-weight: 500; color: var(--text-secondary); }

.text-input, .textarea-input {
  padding: 9px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  font-family: inherit;
  resize: vertical;
}

.text-input:focus, .textarea-input:focus { outline: none; border-color: var(--accent-cyan); }
.text-input:disabled { opacity: 0.5; cursor: not-allowed; }

@media (max-width: 900px) {
  .memory-layout { grid-template-columns: 1fr; }
  .table-header, .table-row { grid-template-columns: 1fr 1.5fr auto auto; }
  .table-header span:nth-child(4),
  .table-header span:nth-child(5),
  .table-row .entry-meta { display: none; }
}
</style>
