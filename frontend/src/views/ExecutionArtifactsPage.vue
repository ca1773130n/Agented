<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);

type ArtifactType = 'diff' | 'report' | 'test_file' | 'log' | 'json';

interface Artifact {
  id: string;
  name: string;
  type: ArtifactType;
  size_kb: number;
  execution_id: string;
  bot_name: string;
  created_at: string;
  download_url: string;
  preview?: string;
}

const artifacts = ref<Artifact[]>([]);
const selectedArtifact = ref<Artifact | null>(null);
const filterType = ref<string>('all');
const searchQuery = ref('');

async function loadArtifacts() {
  try {
    const res = await fetch('/api/executions/artifacts');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    artifacts.value = (await res.json()).artifacts ?? [];
  } catch {
    const now = Date.now();
    artifacts.value = [
      {
        id: 'art-001',
        name: 'security-audit-report.json',
        type: 'report',
        size_kb: 42,
        execution_id: 'ex-abc123',
        bot_name: 'Security Audit',
        created_at: new Date(now - 3600000).toISOString(),
        download_url: '#',
        preview: '{"severity":"high","findings":5,"cves":["CVE-2024-1234","CVE-2024-5678"],"summary":"5 high-severity vulnerabilities found in dependencies"}',
      },
      {
        id: 'art-002',
        name: 'pr-review-diff.patch',
        type: 'diff',
        size_kb: 8,
        execution_id: 'ex-def456',
        bot_name: 'PR Review',
        created_at: new Date(now - 7200000).toISOString(),
        download_url: '#',
        preview: '--- a/src/auth.ts\n+++ b/src/auth.ts\n@@ -12,6 +12,8 @@\n+  // Validate token expiry\n+  if (token.exp < Date.now()) throw new Error("Token expired");\n   return verifyJwt(token);',
      },
      {
        id: 'art-003',
        name: 'generated-tests.ts',
        type: 'test_file',
        size_kb: 15,
        execution_id: 'ex-ghi789',
        bot_name: 'Test Generator',
        created_at: new Date(now - 86400000).toISOString(),
        download_url: '#',
        preview: "import { describe, it, expect } from 'vitest';\nimport { parseWebhook } from '../src/webhooks';\n\ndescribe('parseWebhook', () => {\n  it('parses GitHub PR event', () => {\n    const result = parseWebhook({ action: 'opened' });\n    expect(result.type).toBe('pull_request');\n  });\n});",
      },
      {
        id: 'art-004',
        name: 'execution-stdout.log',
        type: 'log',
        size_kb: 120,
        execution_id: 'ex-jkl012',
        bot_name: 'Dep Check',
        created_at: new Date(now - 172800000).toISOString(),
        download_url: '#',
        preview: '[INFO] Scanning package.json...\n[INFO] Checking 143 packages against NVD database\n[WARN] lodash@4.17.20 → CVE-2021-23337 (CVSS 7.2)\n[INFO] Scan complete. 1 finding.',
      },
      {
        id: 'art-005',
        name: 'changelog-entry.md',
        type: 'report',
        size_kb: 3,
        execution_id: 'ex-mno345',
        bot_name: 'Changelog Bot',
        created_at: new Date(now - 259200000).toISOString(),
        download_url: '#',
        preview: '## v1.4.2 — 2026-03-05\n\n### Fixed\n- Resolved race condition in workflow execution state (#142)\n- Fixed token count overflow for long-running agents (#138)\n\n### Changed\n- ExecutionService now enforces 5-min TTL on completed runs',
      },
    ];
  } finally {
    isLoading.value = false;
  }
}

const filteredArtifacts = computed(() => {
  let list = artifacts.value;
  if (filterType.value !== 'all') list = list.filter(a => a.type === filterType.value);
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    list = list.filter(
      a =>
        a.name.toLowerCase().includes(q) ||
        a.bot_name.toLowerCase().includes(q) ||
        a.execution_id.includes(q),
    );
  }
  return list;
});

function typeIcon(type: ArtifactType): string {
  const icons: Record<ArtifactType, string> = {
    diff: '±',
    report: '■',
    test_file: '▶',
    log: '≡',
    json: '{}',
  };
  return icons[type] ?? '?';
}

function typeColor(type: ArtifactType): string {
  const colors: Record<ArtifactType, string> = {
    diff: '#818cf8',
    report: '#34d399',
    test_file: '#fbbf24',
    log: '#a0a0a0',
    json: '#f87171',
  };
  return colors[type] ?? '#a0a0a0';
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

function downloadArtifact(artifact: Artifact) {
  showToast(`Downloading ${artifact.name}...`, 'success');
}

function selectArtifact(artifact: Artifact) {
  selectedArtifact.value = selectedArtifact.value?.id === artifact.id ? null : artifact;
}

onMounted(loadArtifacts);
</script>

<template>
  <div class="page-container">

    <div class="page-header">
      <div>
        <h1 class="page-title">Execution Output Artifacts</h1>
        <p class="page-subtitle">
          Named files produced by bot executions — reports, diffs, test files, and logs — stored
          persistently for download or downstream bot consumption.
        </p>
      </div>
    </div>

    <div class="filter-bar">
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="Search by name, bot, or execution ID..."
      />
      <div class="type-filters">
        <button
          v-for="t in ['all', 'diff', 'report', 'test_file', 'log', 'json']"
          :key="t"
          class="type-btn"
          :class="{ active: filterType === t }"
          @click="filterType = t"
        >
          {{ t === 'all' ? 'All' : t.replace('_', ' ') }}
        </button>
      </div>
    </div>

    <LoadingState v-if="isLoading" message="Loading artifacts..." />
    <div v-else class="artifacts-layout">
      <div class="artifacts-list">
        <div
          v-for="artifact in filteredArtifacts"
          :key="artifact.id"
          class="artifact-row"
          :class="{ selected: selectedArtifact?.id === artifact.id }"
          @click="selectArtifact(artifact)"
        >
          <div class="artifact-icon" :style="{ color: typeColor(artifact.type) }">
            {{ typeIcon(artifact.type) }}
          </div>
          <div class="artifact-info">
            <span class="artifact-name">{{ artifact.name }}</span>
            <span class="artifact-meta">
              {{ artifact.bot_name }} · ex/{{ artifact.execution_id.slice(-6) }} · {{ artifact.size_kb }}KB · {{ formatTime(artifact.created_at) }}
            </span>
          </div>
          <button
            class="download-btn"
            @click.stop="downloadArtifact(artifact)"
          >
            ↓
          </button>
        </div>
        <p v-if="filteredArtifacts.length === 0" class="empty-msg">No artifacts match your filter.</p>
      </div>

      <!-- Preview panel -->
      <div v-if="selectedArtifact" class="preview-panel">
        <div class="preview-header">
          <div>
            <h3 class="preview-name">{{ selectedArtifact.name }}</h3>
            <p class="preview-meta">
              {{ selectedArtifact.bot_name }} · {{ selectedArtifact.size_kb }}KB ·
              {{ formatTime(selectedArtifact.created_at) }}
            </p>
          </div>
          <button class="download-btn-full" @click="downloadArtifact(selectedArtifact)">
            Download
          </button>
        </div>
        <pre v-if="selectedArtifact.preview" class="preview-code">{{ selectedArtifact.preview }}</pre>
        <p v-else class="preview-unavailable">Preview not available for this artifact type.</p>
      </div>
      <div v-else class="preview-placeholder">
        <p>Select an artifact to preview</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
}
.page-header { margin-bottom: 1.5rem; }
.page-title { font-size: 1.75rem; font-weight: 700; color: var(--color-text-primary, #f0f0f0); margin: 0 0 0.5rem; }
.page-subtitle { color: var(--color-text-secondary, #a0a0a0); margin: 0; }
.filter-bar {
  display: flex;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
}
.search-input {
  flex: 1;
  min-width: 200px;
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  color: var(--color-text-primary, #f0f0f0);
  font-size: 0.875rem;
}
.search-input:focus { outline: none; border-color: var(--color-accent, #6366f1); }
.type-filters { display: flex; gap: 0.4rem; flex-wrap: wrap; }
.type-btn {
  padding: 0.35rem 0.7rem;
  border-radius: 6px;
  border: 1px solid var(--color-border, #2a2a2a);
  background: var(--color-surface, #1a1a1a);
  color: var(--color-text-secondary, #a0a0a0);
  font-size: 0.8rem;
  cursor: pointer;
  text-transform: capitalize;
}
.type-btn.active { border-color: var(--color-accent, #6366f1); color: var(--color-accent, #6366f1); }
.artifacts-layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  align-items: start;
}
@media (max-width: 800px) { .artifacts-layout { grid-template-columns: 1fr; } }
.artifacts-list {
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 8px;
  overflow: hidden;
}
.artifact-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  border-bottom: 1px solid var(--color-border, #2a2a2a);
  cursor: pointer;
  transition: background 0.12s;
}
.artifact-row:last-child { border-bottom: none; }
.artifact-row:hover { background: rgba(255, 255, 255, 0.03); }
.artifact-row.selected { background: rgba(99, 102, 241, 0.08); }
.artifact-icon { font-size: 1.1rem; font-family: monospace; width: 24px; text-align: center; }
.artifact-info { flex: 1; min-width: 0; }
.artifact-name { display: block; font-size: 0.875rem; font-weight: 600; color: var(--color-text-primary, #f0f0f0); font-family: monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.artifact-meta { display: block; font-size: 0.75rem; color: var(--color-text-secondary, #a0a0a0); margin-top: 0.15rem; }
.download-btn {
  width: 28px; height: 28px;
  border-radius: 6px;
  border: 1px solid var(--color-border, #2a2a2a);
  background: var(--color-bg, #111);
  color: var(--color-text-secondary, #a0a0a0);
  font-size: 0.9rem;
  cursor: pointer;
  flex-shrink: 0;
}
.download-btn:hover { border-color: var(--color-accent, #6366f1); color: var(--color-accent, #6366f1); }
.preview-panel {
  background: var(--color-surface, #1a1a1a);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 8px;
  padding: 1.25rem;
}
.preview-placeholder {
  background: var(--color-surface, #1a1a1a);
  border: 1px dashed var(--color-border, #2a2a2a);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--color-text-secondary, #a0a0a0);
  font-size: 0.875rem;
}
.preview-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1rem; gap: 0.5rem; }
.preview-name { font-size: 0.9rem; font-weight: 600; color: var(--color-text-primary, #f0f0f0); font-family: monospace; margin: 0 0 0.25rem; }
.preview-meta { font-size: 0.75rem; color: var(--color-text-secondary, #a0a0a0); margin: 0; }
.download-btn-full {
  padding: 0.4rem 0.75rem;
  border-radius: 6px;
  border: 1px solid var(--color-accent, #6366f1);
  background: transparent;
  color: var(--color-accent, #6366f1);
  font-size: 0.8rem;
  cursor: pointer;
  white-space: nowrap;
}
.preview-code {
  background: var(--color-bg, #111);
  border: 1px solid var(--color-border, #2a2a2a);
  border-radius: 6px;
  padding: 1rem;
  font-family: monospace;
  font-size: 0.8rem;
  color: var(--color-text-primary, #f0f0f0);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  max-height: 400px;
  overflow-y: auto;
}
.preview-unavailable { color: var(--color-text-secondary, #a0a0a0); font-size: 0.875rem; text-align: center; padding: 2rem 0; margin: 0; }
.empty-msg { text-align: center; color: var(--color-text-secondary, #a0a0a0); padding: 2rem; margin: 0; }
</style>
