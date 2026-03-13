<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { executionTaggingApi } from '../services/api/execution-tagging';

const showToast = useToast();

type TagColor = 'blue' | 'green' | 'amber' | 'red' | 'purple';

interface ExecutionTag {
  id: string;
  name: string;
  color: TagColor;
  executionCount: number;
  createdAt: string;
}

interface TaggedExecution {
  id: string;
  botName: string;
  botId: string;
  triggeredAt: string;
  durationMs: number;
  status: 'success' | 'failed' | 'timeout';
  tags: string[];
  logSnippet: string;
  hasMatch?: boolean;
}

const searchQuery = ref('');
const selectedTagIds = ref<string[]>([]);
const showCreateTag = ref(false);
const newTagName = ref('');
const newTagColor = ref<TagColor>('blue');
const addTagTarget = ref<string | null>(null);

const tags = ref<ExecutionTag[]>([]);
const executions = ref<TaggedExecution[]>([]);

function mapApiTag(raw: { id: string; name: string; color: string; execution_count: number; created_at: string }): ExecutionTag {
  return {
    id: raw.id,
    name: raw.name,
    color: raw.color as TagColor,
    executionCount: raw.execution_count,
    createdAt: raw.created_at,
  };
}

function mapApiExecution(raw: {
  id: string;
  trigger_name: string | null;
  bot_id: string | null;
  started_at: string;
  duration_ms: number | null;
  status: string;
  log_snippet: string;
  tags: string[];
}): TaggedExecution {
  return {
    id: raw.id,
    botName: raw.trigger_name ?? 'Unknown Bot',
    botId: raw.bot_id ?? '',
    triggeredAt: raw.started_at,
    durationMs: raw.duration_ms ?? 0,
    status: raw.status as 'success' | 'failed' | 'timeout',
    tags: raw.tags,
    logSnippet: raw.log_snippet ?? '',
  };
}

async function loadTags() {
  try {
    const res = await executionTaggingApi.listTags();
    tags.value = res.tags.map(mapApiTag);
  } catch {
    showToast('Failed to load tags', 'error');
  }
}

async function loadExecutions() {
  try {
    const res = await executionTaggingApi.listExecutions({ limit: 50 });
    executions.value = res.executions.map(mapApiExecution);
  } catch {
    showToast('Failed to load executions', 'error');
  }
}

onMounted(async () => {
  await Promise.all([loadTags(), loadExecutions()]);
});

const filteredExecutions = computed(() => {
  let result = executions.value.map((e) => ({ ...e, hasMatch: false }));

  if (selectedTagIds.value.length > 0) {
    result = result.filter((e) => selectedTagIds.value.every((t) => e.tags.includes(t)));
  }

  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase();
    result = result
      .filter(
        (e) =>
          e.logSnippet.toLowerCase().includes(q) ||
          e.botName.toLowerCase().includes(q) ||
          e.tags.some((t) => {
            const tag = tags.value.find((tg) => tg.id === t);
            return tag?.name.toLowerCase().includes(q);
          })
      )
      .map((e) => ({
        ...e,
        hasMatch: e.logSnippet.toLowerCase().includes(q),
      }));
  }

  return result;
});

function tagForId(id: string): ExecutionTag | undefined {
  return tags.value.find((t) => t.id === id);
}

function tagColorVar(color: TagColor): string {
  const map: Record<TagColor, string> = {
    blue: 'var(--accent-blue)',
    green: 'var(--accent-green)',
    amber: 'var(--accent-amber)',
    red: 'var(--accent-red)',
    purple: '#a78bfa',
  };
  return map[color];
}

function statusColor(status: string): string {
  if (status === 'success') return 'var(--accent-green)';
  if (status === 'failed') return 'var(--accent-red)';
  return 'var(--accent-amber)';
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatDuration(ms: number): string {
  return ms >= 60000 ? `${(ms / 60000).toFixed(1)}m` : `${(ms / 1000).toFixed(1)}s`;
}

function toggleTagFilter(tagId: string) {
  if (selectedTagIds.value.includes(tagId)) {
    selectedTagIds.value = selectedTagIds.value.filter((t) => t !== tagId);
  } else {
    selectedTagIds.value = [...selectedTagIds.value, tagId];
  }
}

async function addTagToExecution(execId: string, tagId: string) {
  addTagTarget.value = null;
  try {
    await executionTaggingApi.addTag(execId, tagId);
    const exec = executions.value.find((e) => e.id === execId);
    if (exec && !exec.tags.includes(tagId)) {
      exec.tags = [...exec.tags, tagId];
    }
    const tag = tags.value.find((t) => t.id === tagId);
    if (tag) tag.executionCount++;
    showToast(`Tag "${tag?.name}" added`, 'success');
  } catch {
    showToast('Failed to add tag', 'error');
  }
}

async function removeTagFromExecution(execId: string, tagId: string) {
  try {
    await executionTaggingApi.removeTag(execId, tagId);
    const exec = executions.value.find((e) => e.id === execId);
    if (exec) {
      exec.tags = exec.tags.filter((t) => t !== tagId);
    }
    const tag = tags.value.find((t) => t.id === tagId);
    if (tag && tag.executionCount > 0) tag.executionCount--;
    showToast('Tag removed', 'info');
  } catch {
    showToast('Failed to remove tag', 'error');
  }
}

async function createTag() {
  if (!newTagName.value.trim()) {
    showToast('Tag name cannot be empty', 'error');
    return;
  }
  try {
    const res = await executionTaggingApi.createTag(newTagName.value.trim(), newTagColor.value);
    tags.value.push(mapApiTag(res.tag));
    showCreateTag.value = false;
    newTagName.value = '';
    showToast('Tag created', 'success');
  } catch {
    showToast('Failed to create tag', 'error');
  }
}

async function deleteTag(tagId: string) {
  try {
    await executionTaggingApi.deleteTag(tagId);
    tags.value = tags.value.filter((t) => t.id !== tagId);
    executions.value.forEach((e) => {
      e.tags = e.tags.filter((t) => t !== tagId);
    });
    selectedTagIds.value = selectedTagIds.value.filter((t) => t !== tagId);
    showToast('Tag deleted', 'info');
  } catch {
    showToast('Failed to delete tag', 'error');
  }
}

function highlightMatch(text: string, query: string): string {
  if (!query.trim()) return text;
  const idx = text.toLowerCase().indexOf(query.toLowerCase());
  if (idx === -1) return text;
  return (
    text.slice(0, idx) +
    `<mark>${text.slice(idx, idx + query.length)}</mark>` +
    text.slice(idx + query.length)
  );
}

const tagColors: TagColor[] = ['blue', 'green', 'amber', 'red', 'purple'];
</script>

<template>
  <div class="page-container">
    <AppBreadcrumb :items="[{ label: 'Executions' }, { label: 'Tagging & Search' }]" />
    <PageHeader
      title="Execution Tagging & Full-Text Search"
      subtitle="Tag executions with labels and search across full log output to quickly find relevant runs"
    />

    <!-- Tag manager -->
    <div class="section-card">
      <div class="section-header">
        <h3 class="section-title">Tags</h3>
        <button class="btn-secondary" @click="showCreateTag = !showCreateTag">+ New Tag</button>
      </div>

      <div v-if="showCreateTag" class="create-tag-row">
        <input v-model="newTagName" class="form-input" placeholder="Tag name…" @keydown.enter="createTag" />
        <div class="color-picker">
          <button
            v-for="c in tagColors"
            :key="c"
            class="color-dot"
            :class="{ selected: newTagColor === c }"
            :style="{ background: tagColorVar(c) }"
            @click="newTagColor = c"
          ></button>
        </div>
        <button class="btn-primary-sm" @click="createTag">Create</button>
        <button class="btn-cancel" @click="showCreateTag = false">Cancel</button>
      </div>

      <div class="tags-row">
        <div
          v-for="tag in tags"
          :key="tag.id"
          class="tag-pill"
          :class="{ active: selectedTagIds.includes(tag.id) }"
          :style="{ '--tag-color': tagColorVar(tag.color) }"
          @click="toggleTagFilter(tag.id)"
        >
          <span class="tag-dot" :style="{ background: tagColorVar(tag.color) }"></span>
          {{ tag.name }}
          <span class="tag-count">{{ tag.executionCount }}</span>
          <button class="tag-delete-btn" @click.stop="deleteTag(tag.id)">✕</button>
        </div>
        <button
          v-if="selectedTagIds.length > 0"
          class="clear-filter"
          @click="selectedTagIds = []"
        >
          Clear filters
        </button>
      </div>
    </div>

    <!-- Search -->
    <div class="search-bar">
      <span class="search-icon">🔍</span>
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="Search execution logs, bot names, or tags…"
      />
      <span v-if="searchQuery" class="search-clear" @click="searchQuery = ''">✕</span>
    </div>

    <!-- Results summary -->
    <div class="results-meta">
      <span>
        {{ filteredExecutions.length }} execution{{ filteredExecutions.length !== 1 ? 's' : '' }}
        <template v-if="selectedTagIds.length > 0"> · filtered by {{ selectedTagIds.length }} tag{{ selectedTagIds.length !== 1 ? 's' : '' }}</template>
        <template v-if="searchQuery"> · matching "{{ searchQuery }}"</template>
      </span>
    </div>

    <!-- Execution list -->
    <div class="executions-list">
      <div v-for="exec in filteredExecutions" :key="exec.id" class="exec-card">
        <div class="exec-header">
          <div class="exec-info">
            <span :style="{ color: statusColor(exec.status) }">● </span>
            <span class="exec-bot">{{ exec.botName }}</span>
            <span class="exec-meta">{{ formatDate(exec.triggeredAt) }} · {{ formatDuration(exec.durationMs) }}</span>
          </div>
          <div class="exec-tag-controls">
            <div class="exec-tags">
              <span
                v-for="tagId in exec.tags"
                :key="tagId"
                class="exec-tag"
                :style="{ '--tag-color': tagForId(tagId) ? tagColorVar(tagForId(tagId)!.color) : 'var(--text-muted)' }"
              >
                {{ tagForId(tagId)?.name ?? tagId }}
                <button class="exec-tag-remove" @click="removeTagFromExecution(exec.id, tagId)">✕</button>
              </span>
            </div>
            <div class="add-tag-dropdown-wrap">
              <button class="btn-add-tag" @click="addTagTarget = addTagTarget === exec.id ? null : exec.id">+ Tag</button>
              <div v-if="addTagTarget === exec.id" class="tag-dropdown">
                <div
                  v-for="tag in tags.filter(t => !exec.tags.includes(t.id))"
                  :key="tag.id"
                  class="tag-option"
                  @click="addTagToExecution(exec.id, tag.id)"
                >
                  <span class="tag-dot" :style="{ background: tagColorVar(tag.color) }"></span>
                  {{ tag.name }}
                </div>
                <div v-if="tags.filter(t => !exec.tags.includes(t.id)).length === 0" class="tag-option muted">
                  All tags applied
                </div>
              </div>
            </div>
          </div>
        </div>
        <div
          class="exec-log"
          :class="{ highlight: exec.hasMatch }"
          v-html="exec.hasMatch ? highlightMatch(exec.logSnippet, searchQuery) : exec.logSnippet"
        ></div>
        <div v-if="exec.hasMatch && searchQuery" class="match-note">
          Log match found for "{{ searchQuery }}"
        </div>
      </div>

      <div v-if="filteredExecutions.length === 0" class="empty-state">
        <div class="empty-icon">🔍</div>
        <div class="empty-text">No executions match your filters</div>
        <button class="btn-secondary" @click="searchQuery = ''; selectedTagIds = []">Clear all filters</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container { padding: 24px; max-width: 1000px; }
.section-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin: 0; }
.create-tag-row { display: flex; align-items: center; gap: 10px; padding: 12px 0; border-bottom: 1px solid var(--border-color); margin-bottom: 12px; flex-wrap: wrap; }
.form-input { padding: 7px 12px; border: 1px solid var(--border-color); border-radius: 6px; background: var(--bg-primary); color: var(--text-primary); font-size: 13px; }
.color-picker { display: flex; gap: 6px; }
.color-dot { width: 18px; height: 18px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; }
.color-dot.selected { border-color: white; transform: scale(1.2); }
.btn-primary-sm { padding: 5px 12px; border-radius: 5px; border: none; background: var(--accent-blue); color: white; cursor: pointer; font-size: 12px; font-weight: 600; }
.btn-cancel { padding: 5px 12px; border-radius: 5px; border: 1px solid var(--border-color); background: transparent; color: var(--text-muted); cursor: pointer; font-size: 12px; }
.tags-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.tag-pill { display: flex; align-items: center; gap: 5px; padding: 5px 12px; border-radius: 16px; border: 1px solid var(--border-color); background: transparent; cursor: pointer; font-size: 12px; color: var(--text-muted); transition: all 0.15s; user-select: none; }
.tag-pill.active { background: color-mix(in srgb, var(--tag-color) 15%, transparent); border-color: var(--tag-color); color: var(--tag-color); }
.tag-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.tag-count { font-size: 10px; opacity: 0.7; }
.tag-delete-btn { background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-size: 10px; padding: 0; margin-left: 2px; }
.clear-filter { padding: 5px 12px; border-radius: 16px; border: 1px dashed var(--border-color); background: transparent; color: var(--text-muted); cursor: pointer; font-size: 12px; }
.search-bar { display: flex; align-items: center; gap: 10px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 16px; margin-bottom: 12px; }
.search-icon { font-size: 14px; }
.search-input { flex: 1; background: transparent; border: none; color: var(--text-primary); font-size: 14px; outline: none; }
.search-input::placeholder { color: var(--text-muted); }
.search-clear { color: var(--text-muted); cursor: pointer; font-size: 13px; }
.results-meta { font-size: 12px; color: var(--text-muted); margin-bottom: 12px; }
.executions-list { display: flex; flex-direction: column; gap: 10px; }
.exec-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; }
.exec-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.exec-info { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.exec-bot { font-weight: 600; color: var(--text-primary); font-size: 14px; }
.exec-meta { font-size: 11px; color: var(--text-muted); }
.exec-tag-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.exec-tags { display: flex; gap: 5px; flex-wrap: wrap; }
.exec-tag { display: flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 10px; font-size: 11px; background: color-mix(in srgb, var(--tag-color) 15%, transparent); color: var(--tag-color); border: 1px solid color-mix(in srgb, var(--tag-color) 30%, transparent); }
.exec-tag-remove { background: transparent; border: none; color: inherit; cursor: pointer; font-size: 9px; padding: 0; opacity: 0.7; }
.add-tag-dropdown-wrap { position: relative; }
.btn-add-tag { padding: 3px 8px; border-radius: 5px; border: 1px dashed var(--border-color); background: transparent; color: var(--text-muted); cursor: pointer; font-size: 11px; }
.tag-dropdown { position: absolute; top: 100%; right: 0; z-index: 100; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 4px; min-width: 140px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); margin-top: 4px; }
.tag-option { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 5px; cursor: pointer; font-size: 12px; color: var(--text-primary); }
.tag-option:hover { background: var(--bg-hover); }
.tag-option.muted { color: var(--text-muted); cursor: default; }
.exec-log { font-size: 12px; color: var(--text-muted); line-height: 1.6; background: var(--bg-primary); border-radius: 6px; padding: 10px 12px; font-family: monospace; white-space: pre-wrap; word-break: break-word; }
.exec-log.highlight { border-left: 3px solid var(--accent-blue); }
.exec-log :deep(mark) { background: color-mix(in srgb, var(--accent-amber) 35%, transparent); color: var(--text-primary); border-radius: 2px; padding: 0 1px; }
.match-note { font-size: 11px; color: var(--accent-blue); margin-top: 6px; }
.empty-state { text-align: center; padding: 40px; color: var(--text-muted); }
.empty-icon { font-size: 32px; margin-bottom: 12px; }
.empty-text { font-size: 14px; margin-bottom: 16px; }
.btn-secondary { padding: 7px 16px; border-radius: 6px; border: 1px solid var(--border-color); background: transparent; color: var(--text-primary); cursor: pointer; font-size: 13px; }
</style>
