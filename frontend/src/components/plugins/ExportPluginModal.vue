<script setup lang="ts">
import { ref, computed, toRef } from 'vue';
import type { PluginExportResponse } from '../../services/api';
import { pluginExportApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  show: boolean;
  teams: Array<{ id: string; name: string }>;
  preSelectedTeamId?: string;
  pluginId?: string | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'exported', result: PluginExportResponse): void;
}>();

const showToast = useToast();

const exportModalRef = ref<HTMLElement | null>(null);
const isOpen = toRef(props, 'show');
useFocusTrap(exportModalRef, isOpen);

const selectedTeamId = ref(props.preSelectedTeamId || '');
const exportFormat = ref<'claude' | 'agented'>('claude');
const outputDir = ref('');
const isExporting = ref(false);
const exportResult = ref<PluginExportResponse | null>(null);
const copiedPath = ref(false);

const canExport = computed(() => !!selectedTeamId.value && !isExporting.value);

function resetState() {
  selectedTeamId.value = props.preSelectedTeamId || '';
  exportFormat.value = 'claude';
  outputDir.value = '';
  isExporting.value = false;
  exportResult.value = null;
  copiedPath.value = false;
}

function handleClose() {
  resetState();
  emit('close');
}

async function doExport() {
  if (!canExport.value) return;
  isExporting.value = true;
  try {
    const result = await pluginExportApi.export({
      team_id: selectedTeamId.value,
      export_format: exportFormat.value,
      output_dir: outputDir.value || undefined,
      plugin_id: props.pluginId || undefined,
    });
    exportResult.value = result;
    emit('exported', result);
    showToast(`Exported "${result.plugin_name}" as ${result.format}`, 'success');
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to export plugin', 'error');
    }
  } finally {
    isExporting.value = false;
  }
}

async function copyPath() {
  if (!exportResult.value) return;
  try {
    await navigator.clipboard.writeText(exportResult.value.export_path);
    copiedPath.value = true;
    setTimeout(() => { copiedPath.value = false; }, 2000);
  } catch {
    showToast('Failed to copy path', 'error');
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" ref="exportModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-export-plugin" tabindex="-1" @click.self="handleClose" @keydown.escape="handleClose">
      <div class="modal export-modal">
        <div class="modal-header">
          <h2 id="modal-title-export-plugin">Export as Plugin</h2>
          <button class="modal-close" @click="handleClose">&times;</button>
        </div>

        <div class="modal-body">
          <!-- Export Form -->
          <template v-if="!exportResult">
            <div v-if="props.pluginId" class="context-info">
              Exporting specific plugin
            </div>
            <div class="form-group">
              <label>Team *</label>
              <select v-model="selectedTeamId" :disabled="isExporting">
                <option value="" disabled>Select a team</option>
                <option v-for="team in teams" :key="team.id" :value="team.id">
                  {{ team.name }}
                </option>
              </select>
              <p v-if="teams.length === 0" class="hint-text">No teams available</p>
            </div>

            <div class="form-group">
              <label>Export Format</label>
              <div class="format-cards">
                <div
                  class="format-card"
                  :class="{ active: exportFormat === 'claude' }"
                  @click="exportFormat = 'claude'"
                >
                  <div class="format-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                    </svg>
                  </div>
                  <div class="format-text">
                    <strong>Claude Code Plugin</strong>
                    <span>Valid .claude-plugin directory for Claude Code</span>
                  </div>
                </div>

                <div
                  class="format-card"
                  :class="{ active: exportFormat === 'agented' }"
                  @click="exportFormat = 'agented'"
                >
                  <div class="format-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                      <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>
                      <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                      <line x1="12" y1="22.08" x2="12" y2="12"/>
                    </svg>
                  </div>
                  <div class="format-text">
                    <strong>Agented Package</strong>
                    <span>Standalone agented.json with embedded entities</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="form-group">
              <label>Output Directory (optional)</label>
              <input
                v-model="outputDir"
                type="text"
                placeholder="Leave blank for auto-generated temp directory"
                :disabled="isExporting"
              />
            </div>
          </template>

          <!-- Export Success -->
          <template v-else>
            <div class="success-panel">
              <div class="success-header">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
                  <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                <h3>Export Successful</h3>
              </div>

              <div class="result-summary">
                <div class="result-row">
                  <span class="result-label">Plugin</span>
                  <span class="result-value">{{ exportResult.plugin_name }}</span>
                </div>
                <div class="result-row">
                  <span class="result-label">Format</span>
                  <span class="result-value format-badge">{{ exportResult.format }}</span>
                </div>
                <div class="result-counts">
                  <div class="count-item" v-if="exportResult.agents > 0">
                    <span class="count-num">{{ exportResult.agents }}</span>
                    <span class="count-label">Agents</span>
                  </div>
                  <div class="count-item" v-if="exportResult.skills > 0">
                    <span class="count-num">{{ exportResult.skills }}</span>
                    <span class="count-label">Skills</span>
                  </div>
                  <div class="count-item" v-if="exportResult.commands > 0">
                    <span class="count-num">{{ exportResult.commands }}</span>
                    <span class="count-label">Commands</span>
                  </div>
                  <div class="count-item" v-if="exportResult.hooks > 0">
                    <span class="count-num">{{ exportResult.hooks }}</span>
                    <span class="count-label">Hooks</span>
                  </div>
                  <div class="count-item" v-if="exportResult.rules > 0">
                    <span class="count-num">{{ exportResult.rules }}</span>
                    <span class="count-label">Rules</span>
                  </div>
                </div>
                <div class="result-path">
                  <span class="result-label">Path</span>
                  <div class="path-row">
                    <code>{{ exportResult.export_path }}</code>
                    <button class="btn btn-small btn-copy" @click="copyPath">
                      {{ copiedPath ? 'Copied!' : 'Copy Path' }}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="handleClose">
            {{ exportResult ? 'Close' : 'Cancel' }}
          </button>
          <button
            v-if="!exportResult"
            class="btn btn-primary"
            :disabled="!canExport"
            @click="doExport"
          >
            {{ isExporting ? 'Exporting...' : 'Export' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>

.export-modal {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 16px;
  width: 100%;
  max-width: 560px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header h2 { font-size: 1.25rem; font-weight: 600; }

.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-secondary, #888);
  cursor: pointer;
}

.form-group input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.context-info {
  font-size: 0.85rem;
  color: var(--accent-cyan, #00d4ff);
  background: rgba(0, 212, 255, 0.1);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 16px;
}

.hint-text {
  color: var(--text-secondary, #888);
  font-size: 0.85rem;
  margin-top: 0.5rem;
}

.format-cards {
  display: flex;
  gap: 0.75rem;
}

.format-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 1.25rem 1rem;
  background: var(--bg-tertiary, #1a1a24);
  border: 2px solid var(--border-default);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}

.format-card:hover {
  border-color: rgba(136, 85, 255, 0.5);
}

.format-card.active {
  border-color: var(--accent-violet, #8855ff);
  background: rgba(136, 85, 255, 0.1);
}

.format-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.format-icon svg {
  width: 28px;
  height: 28px;
  color: var(--accent-violet, #8855ff);
}

.format-text strong {
  display: block;
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
}

.format-text span {
  display: block;
  font-size: 0.75rem;
  color: var(--text-secondary, #888);
}

/* Success panel */
.success-panel {
  text-align: center;
}

.success-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
}

.success-header svg {
  width: 28px;
  height: 28px;
  color: #00ff88;
}

.success-header h3 {
  font-size: 1.15rem;
  color: #00ff88;
}

.result-summary {
  background: var(--bg-tertiary, #1a1a24);
  border-radius: 10px;
  padding: 1.25rem;
  text-align: left;
}

.result-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
}

.result-row + .result-row {
  border-top: 1px solid var(--border-default);
}

.result-label {
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
}

.result-value {
  font-weight: 500;
}

.format-badge {
  font-size: 0.8rem;
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  background: rgba(136, 85, 255, 0.2);
  color: var(--accent-violet, #8855ff);
  font-family: monospace;
}

.result-counts {
  display: flex;
  gap: 1rem;
  justify-content: center;
  padding: 1rem 0;
  border-top: 1px solid var(--border-default);
  border-bottom: 1px solid var(--border-default);
  margin: 0.5rem 0;
}

.count-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.count-num {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--accent-cyan, #00d4ff);
}

.count-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  color: var(--text-secondary, #888);
}

.result-path {
  padding-top: 0.75rem;
}

.result-path .result-label {
  display: block;
  margin-bottom: 0.5rem;
}

.path-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.path-row code {
  flex: 1;
  font-size: 0.8rem;
  background: var(--bg-secondary, #12121a);
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  color: var(--text-primary, #fff);
  word-break: break-all;
}

/* Buttons */

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(136, 85, 255, 0.3);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-default);
}

.btn-small {
  padding: 0.4rem 0.75rem;
  font-size: 0.8rem;
}

.btn-copy {
  background: rgba(136, 85, 255, 0.2);
  color: var(--accent-violet, #8855ff);
  border: 1px solid rgba(136, 85, 255, 0.3);
  white-space: nowrap;
}

.btn-copy:hover {
  background: rgba(136, 85, 255, 0.3);
}
</style>
