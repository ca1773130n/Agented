<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import type { FileNode } from '../services/api';
import { skillsApi, userSkillsApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const showToast = useToast();

const skills = ref<{ name: string; description?: string }[]>([]);
const selectedSkill = ref<string>('');
const testInput = ref('');
const isLoading = ref(true);
const isRunning = ref(false);
const testOutput = ref<string[]>([]);
const testStatus = ref<'idle' | 'running' | 'completed' | 'failed'>('idle');
const eventSource = ref<EventSource | null>(null);
const searchQuery = ref('');
const outputRef = ref<HTMLElement | null>(null);
const currentTestId = ref<string | null>(null);

// File browser state
const playgroundFiles = ref<FileNode[]>([]);
const workingDir = ref('');
const isLoadingFiles = ref(false);
const expandedDirs = ref<Set<string>>(new Set());
const showFileBrowser = ref(true);

const filteredSkills = computed(() => {
  if (!searchQuery.value) return skills.value;
  const q = searchQuery.value.toLowerCase();
  return skills.value.filter(s =>
    s.name.toLowerCase().includes(q) ||
    (s.description && s.description.toLowerCase().includes(q))
  );
});

useWebMcpTool({
  name: 'hive_skills_playground_get_state',
  description: 'Returns the current state of the SkillsPlayground',
  page: 'SkillsPlayground',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'SkillsPlayground',
        skillsCount: skills.value.length,
        selectedSkill: selectedSkill.value || null,
        isLoading: isLoading.value,
        isRunning: isRunning.value,
        testStatus: testStatus.value,
        outputLineCount: testOutput.value.length,
        showFileBrowser: showFileBrowser.value,
      }),
    }],
  }),
  deps: [skills, selectedSkill, isLoading, isRunning, testStatus, testOutput, showFileBrowser],
});

watch(testOutput, () => {
  nextTick(() => {
    if (outputRef.value) {
      outputRef.value.scrollTop = outputRef.value.scrollHeight;
    }
  });
}, { deep: true });

async function loadSkills() {
  isLoading.value = true;
  try {
    const data = await userSkillsApi.list();
    skills.value = (data.skills || []).map(s => ({
      name: s.skill_name,
      description: s.description || undefined,
    }));
  } catch (e) {
    showToast('Failed to load skills', 'error');
  } finally {
    isLoading.value = false;
  }
}

async function loadPlaygroundFiles() {
  isLoadingFiles.value = true;
  try {
    const data = await skillsApi.getPlaygroundFiles();
    playgroundFiles.value = data.files || [];
    workingDir.value = data.working_dir || '';
  } catch (e) {
    // Silent fail - file browser is optional
  } finally {
    isLoadingFiles.value = false;
  }
}

function toggleDir(path: string) {
  if (expandedDirs.value.has(path)) {
    expandedDirs.value.delete(path);
  } else {
    expandedDirs.value.add(path);
  }
}

async function runTest() {
  if (!selectedSkill.value || isRunning.value) return;

  testOutput.value = [];
  testStatus.value = 'running';
  isRunning.value = true;

  try {
    const result = await skillsApi.test(selectedSkill.value, testInput.value);
    currentTestId.value = result.test_id;
    connectToStream(result.test_id);
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to start test', 'error');
    }
    isRunning.value = false;
    testStatus.value = 'failed';
  }
}

function connectToStream(testId: string) {
  if (eventSource.value) {
    eventSource.value.close();
  }

  eventSource.value = skillsApi.streamTest(testId);

  eventSource.value.addEventListener('start', () => {
    testOutput.value.push(`> Testing skill: ${selectedSkill.value}`);
    testOutput.value.push('');
  });

  eventSource.value.addEventListener('output', (event) => {
    const data = JSON.parse(event.data);
    testOutput.value.push(data.content);
  });

  eventSource.value.addEventListener('error_output', (event) => {
    const data = JSON.parse(event.data);
    testOutput.value.push(`[stderr] ${data.content}`);
  });

  eventSource.value.addEventListener('complete', (event) => {
    const data = JSON.parse(event.data);
    testStatus.value = data.status === 'completed' ? 'completed' : 'failed';
    testOutput.value.push('');
    testOutput.value.push(`> Test ${data.status} (exit code: ${data.exit_code ?? 'unknown'})`);
    isRunning.value = false;
    eventSource.value?.close();
  });

  eventSource.value.addEventListener('error', (event) => {
    try {
      const data = JSON.parse((event as MessageEvent).data || '{}');
      testOutput.value.push(`[error] ${data.error || 'Unknown error'}`);
    } catch {
      testOutput.value.push('[error] Connection lost');
    }
    testStatus.value = 'failed';
    isRunning.value = false;
  });

  eventSource.value.onerror = () => {
    // Connection lost
    isRunning.value = false;
  };
}

function clearOutput() {
  testOutput.value = [];
  testStatus.value = 'idle';
}

async function stopTest() {
  if (currentTestId.value) {
    try {
      await skillsApi.stopTest(currentTestId.value);
    } catch {
      // Still close the stream even if stop request fails
    }
  }
  if (eventSource.value) {
    eventSource.value.close();
    eventSource.value = null;
  }
  isRunning.value = false;
  testStatus.value = 'idle';
  testOutput.value.push('');
  testOutput.value.push('> Test stopped by user');
}

onMounted(() => {
  loadSkills();
  loadPlaygroundFiles();
});

onUnmounted(() => {
  if (eventSource.value) {
    eventSource.value.close();
  }
});
</script>

<template>
  <div class="playground-page">
    <AppBreadcrumb :items="[{ label: 'Skills', action: () => router.push({ name: 'my-skills' }) }, { label: 'Playground' }]" />
    <div class="page-header">
      <div class="header-content">
        <h1>Skills Playground</h1>
        <p class="subtitle">Test and experiment with Claude skills in a sandbox environment</p>
      </div>
    </div>

    <div class="playground-layout" :class="{ 'files-collapsed': !showFileBrowser }">
      <!-- Skill Selection Panel -->
      <div class="skill-panel">
        <div class="panel-header">
          <h3>Available Skills</h3>
          <button class="btn-refresh" @click="loadSkills" :disabled="isLoading">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ spinning: isLoading }">
              <path d="M1 4v6h6M23 20v-6h-6"/>
              <path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15"/>
            </svg>
          </button>
        </div>

        <div class="search-box">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search skills..."
          />
        </div>

        <div v-if="isLoading" class="loading-state">
          <div class="spinner"></div>
          <span>Loading skills...</span>
        </div>

        <div v-else-if="filteredSkills.length === 0" class="empty-skills">
          <p>No skills found</p>
        </div>

        <div v-else class="skills-list">
          <div
            v-for="skill in filteredSkills"
            :key="skill.name"
            class="skill-item"
            :class="{ selected: selectedSkill === skill.name }"
            @click="selectedSkill = skill.name"
          >
            <div class="skill-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
              </svg>
            </div>
            <div class="skill-info">
              <span class="skill-name">{{ skill.name }}</span>
              <span v-if="skill.description" class="skill-desc">{{ skill.description }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Test Panel -->
      <div class="test-panel">
        <div class="panel-header">
          <h3>Test Execution</h3>
          <div class="test-status" :class="testStatus">
            <span class="status-dot"></span>
            <span>{{ testStatus === 'idle' ? 'Ready' : testStatus }}</span>
          </div>
        </div>

        <div class="input-section">
          <label>Selected Skill</label>
          <div class="selected-skill">
            <span v-if="selectedSkill" class="skill-badge">{{ selectedSkill }}</span>
            <span v-else class="no-selection">Select a skill from the list</span>
          </div>

          <label>Test Input <span class="optional">(optional)</span></label>
          <textarea
            v-model="testInput"
            placeholder="Enter test input or prompt..."
            rows="4"
            :disabled="isRunning"
          ></textarea>

          <div class="test-actions">
            <button
              class="btn btn-primary"
              @click="runTest"
              :disabled="!selectedSkill || isRunning"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              {{ isRunning ? 'Running...' : 'Run Test' }}
            </button>
            <button
              v-if="isRunning"
              class="btn btn-danger"
              @click="stopTest"
            >
              <svg viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12"/>
              </svg>
              Stop
            </button>
            <button
              v-if="testOutput.length > 0 && !isRunning"
              class="btn"
              @click="clearOutput"
            >
              Clear
            </button>
          </div>
        </div>

        <div class="output-section">
          <label>Output</label>
          <div ref="outputRef" class="output-container" :class="{ empty: testOutput.length === 0 }">
            <div v-if="testOutput.length === 0" class="output-placeholder">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <line x1="3" y1="9" x2="21" y2="9"/>
                <line x1="9" y1="21" x2="9" y2="9"/>
              </svg>
              <span>Output will appear here</span>
            </div>
            <pre v-else><code>{{ testOutput.join('\n') }}</code></pre>
          </div>
        </div>
      </div>

      <!-- File Browser Panel -->
      <div class="file-panel" :class="{ collapsed: !showFileBrowser }">
        <div class="panel-header">
          <h3>Codebase</h3>
          <button class="btn-toggle" @click="showFileBrowser = !showFileBrowser">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path v-if="showFileBrowser" d="M15 19l-7-7 7-7"/>
              <path v-else d="M9 5l7 7-7 7"/>
            </svg>
          </button>
        </div>

        <template v-if="showFileBrowser">
          <div class="working-dir" v-if="workingDir">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"/>
              <path d="M9 22V12h6v10"/>
            </svg>
            <span class="dir-path" :title="workingDir">{{ workingDir.split('/').pop() || workingDir }}</span>
          </div>

          <div v-if="isLoadingFiles" class="loading-state small">
            <div class="spinner"></div>
            <span>Loading files...</span>
          </div>

          <div v-else-if="playgroundFiles.length === 0" class="empty-files">
            <p>No files found</p>
          </div>

          <div v-else class="file-tree">
            <template v-for="node in playgroundFiles" :key="node.path">
              <div
                class="file-node"
                :class="{ directory: node.type === 'directory', expanded: expandedDirs.has(node.path) }"
                @click="node.type === 'directory' && toggleDir(node.path)"
              >
                <span class="node-icon">
                  <svg v-if="node.type === 'directory'" viewBox="0 0 24 24" fill="currentColor">
                    <path v-if="expandedDirs.has(node.path)" d="M19 11H5a1 1 0 00-1 1v9a1 1 0 001 1h14a1 1 0 001-1v-9a1 1 0 00-1-1zm-14-1L7 6a1 1 0 011-1h5l2 3h5v2H5z"/>
                    <path v-else d="M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z"/>
                  </svg>
                  <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                    <path d="M14 2v6h6"/>
                  </svg>
                </span>
                <span class="node-name">{{ node.name }}</span>
              </div>
              <template v-if="node.type === 'directory' && node.children && expandedDirs.has(node.path)">
                <div
                  v-for="child in node.children"
                  :key="child.path"
                  class="file-node nested"
                  :class="{ directory: child.type === 'directory', expanded: expandedDirs.has(child.path) }"
                  @click="child.type === 'directory' && toggleDir(child.path)"
                >
                  <span class="node-icon">
                    <svg v-if="child.type === 'directory'" viewBox="0 0 24 24" fill="currentColor">
                      <path v-if="expandedDirs.has(child.path)" d="M19 11H5a1 1 0 00-1 1v9a1 1 0 001 1h14a1 1 0 001-1v-9a1 1 0 00-1-1zm-14-1L7 6a1 1 0 011-1h5l2 3h5v2H5z"/>
                      <path v-else d="M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2z"/>
                    </svg>
                    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                      <path d="M14 2v6h6"/>
                    </svg>
                  </span>
                  <span class="node-name">{{ child.name }}</span>
                </div>
              </template>
            </template>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.playground-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100vh;
  overflow: hidden;
}

.page-header {
  margin-bottom: 24px;
}

.header-content h1 {
  font-size: 28px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.subtitle {
  color: var(--text-secondary);
  margin: 0;
}

.playground-layout {
  display: grid;
  grid-template-columns: 280px 1fr 260px;
  gap: 24px;
  flex: 1;
  min-height: 0;
  transition: grid-template-columns 0.3s ease;
}

.playground-layout.files-collapsed {
  grid-template-columns: 280px 1fr 48px;
}

.skill-panel, .test-panel, .file-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.file-panel.collapsed {
  overflow: hidden;
}

.file-panel.collapsed .panel-header h3 {
  display: none;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.panel-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-refresh {
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-refresh svg {
  width: 16px;
  height: 16px;
}

.btn-refresh svg.spinning {
  animation: spin 1s linear infinite;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 16px;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
}

.search-box svg {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.search-box input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
}

.search-box input::placeholder {
  color: var(--text-tertiary);
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 12px;
}

.empty-skills {
  padding: 40px 20px;
  text-align: center;
  color: var(--text-tertiary);
}

.skills-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 12px 12px;
}

.skill-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: 4px;
}

.skill-item:hover {
  background: var(--bg-tertiary);
}

.skill-item.selected {
  background: var(--accent-cyan-dim);
  border: 1px solid var(--accent-cyan);
}

.skill-icon {
  width: 36px;
  height: 36px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.skill-item.selected .skill-icon {
  background: var(--accent-cyan);
}

.skill-icon svg {
  width: 18px;
  height: 18px;
  color: var(--text-secondary);
}

.skill-item.selected .skill-icon svg {
  color: #000;
}

.skill-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.skill-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.skill-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.test-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-tertiary);
}

.test-status.running .status-dot {
  background: var(--accent-amber);
  animation: pulse 1s infinite;
}

.test-status.completed .status-dot {
  background: var(--accent-emerald);
}

.test-status.failed .status-dot {
  background: var(--accent-crimson);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.input-section {
  padding: 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.input-section label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.input-section label .optional {
  font-weight: 400;
  color: var(--text-tertiary);
}

.selected-skill {
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  margin-bottom: 16px;
}

.skill-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  background: var(--accent-cyan-dim);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--accent-cyan);
}

.no-selection {
  color: var(--text-tertiary);
  font-size: 14px;
}

.input-section textarea {
  width: 100%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 12px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
}

.input-section textarea:focus {
  border-color: var(--accent-cyan);
}

.input-section textarea::placeholder {
  color: var(--text-tertiary);
}

.test-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.btn:hover:not(:disabled) {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.btn-primary:hover:not(:disabled) {
  background: #00c4ee;
}

.btn-danger:hover:not(:disabled) {
  background: rgba(255, 51, 102, 0.25);
}

.output-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 20px;
  min-height: 0;
}

.output-section label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.output-container {
  flex: 1;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  overflow: auto;
  min-height: 200px;
}

.output-container.empty {
  display: flex;
  align-items: center;
  justify-content: center;
}

.output-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--text-tertiary);
}

.output-placeholder svg {
  width: 40px;
  height: 40px;
}

.output-container pre {
  margin: 0;
  padding: 16px;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.output-container code {
  font-family: inherit;
}

/* File Browser Panel */
.file-panel {
  transition: width 0.2s;
}

.btn-toggle {
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.btn-toggle:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-toggle svg {
  width: 14px;
  height: 14px;
}

.working-dir {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-subtle);
}

.working-dir svg {
  width: 16px;
  height: 16px;
  color: var(--accent-cyan);
  flex-shrink: 0;
}

.dir-path {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.loading-state.small {
  padding: 20px;
}

.loading-state.small .spinner {
  width: 18px;
  height: 18px;
  margin-bottom: 8px;
}

.empty-files {
  padding: 24px 16px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.file-tree {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.file-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: default;
  user-select: none;
}

.file-node.directory {
  cursor: pointer;
}

.file-node.directory:hover {
  background: var(--bg-tertiary);
}

.file-node.nested {
  padding-left: 28px;
}

.node-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.node-icon svg {
  width: 14px;
  height: 14px;
}

.file-node.directory .node-icon svg {
  color: var(--accent-amber);
}

.node-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
