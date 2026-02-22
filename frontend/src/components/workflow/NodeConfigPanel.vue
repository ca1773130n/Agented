<script setup lang="ts">
/**
 * NodeConfigPanel — Node configuration editor with per-type forms.
 *
 * When a node is selected on the canvas, this panel shows editable config
 * fields specific to that node type. Changes are emitted with debouncing.
 */

import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import type { Node } from '@vue-flow/core'
import type { WorkflowNodeData } from '../../types/workflow'
import { agentApi } from '../../services/api/agents'
import { skillsApi } from '../../services/api/skills'
import { commandApi } from '../../services/api/commands'
import { triggerApi } from '../../services/api/triggers'
import type { Agent, SkillInfo, Command, Trigger } from '../../services/api/types'

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------

const props = defineProps<{
  node: Node | null
  readOnly?: boolean
}>()

const emit = defineEmits<{
  'update-config': [nodeId: string, config: Record<string, unknown>]
  'update-label': [nodeId: string, label: string]
  'delete-node': [nodeId: string]
  close: []
}>()

// ---------------------------------------------------------------------------
// Local config state (synced from node prop)
// ---------------------------------------------------------------------------

const localLabel = ref('')
const localConfig = ref<Record<string, unknown>>({})
const localErrorMode = ref('stop')
const localRetryMax = ref(0)
const localRetryBackoff = ref(1)

const showDeleteConfirm = ref(false)

// ---------------------------------------------------------------------------
// Entity lists for dropdowns
// ---------------------------------------------------------------------------

const agents = ref<Agent[]>([])
const skills = ref<SkillInfo[]>([])
const commands = ref<Command[]>([])
const triggers = ref<Trigger[]>([])
const entitiesLoading = ref(false)

onMounted(async () => {
  entitiesLoading.value = true
  try {
    const [agentRes, skillRes, cmdRes, trigRes] = await Promise.all([
      agentApi.list().catch(() => ({ agents: [] })),
      skillsApi.list().catch(() => ({ skills: [] })),
      commandApi.list().catch(() => ({ commands: [] })),
      triggerApi.list().catch(() => ({ triggers: [] })),
    ])
    agents.value = agentRes.agents
    skills.value = skillRes.skills
    commands.value = cmdRes.commands
    triggers.value = trigRes.triggers
  } finally {
    entitiesLoading.value = false
  }
})

// ---------------------------------------------------------------------------
// Entity selection handlers
// ---------------------------------------------------------------------------

function onAgentSelected(agentId: string) {
  const agent = agents.value.find((a) => a.id === agentId)
  setConfigField('agent_id', agentId)
  setConfigField('agent_name', agent?.name || '')
}

function onSkillSelected(skillName: string) {
  setConfigField('skill_name', skillName)
}

function onCommandSelected(commandIdStr: string) {
  const cmd = commands.value.find((c) => String(c.id) === commandIdStr)
  setConfigField('command_id', commandIdStr ? Number(commandIdStr) : null)
  setConfigField('command_name', cmd?.name || '')
  if (cmd?.content) {
    setConfigField('command', cmd.content)
  }
}

function onTriggerSelected(triggerId: string) {
  const trigger = triggers.value.find((t) => t.id === triggerId)
  setConfigField('trigger_id', triggerId || null)
  setConfigField('trigger_name', trigger?.name || '')
}

// Sync from node prop when selection changes
watch(
  () => props.node,
  (newNode) => {
    showDeleteConfirm.value = false
    if (!newNode) return
    const data = newNode.data as WorkflowNodeData
    localLabel.value = data?.label || ''
    localConfig.value = { ...(data?.config || {}) }
    localErrorMode.value = data?.error_mode || 'stop'
    localRetryMax.value = data?.retry_max ?? 0
    localRetryBackoff.value = data?.retry_backoff_seconds ?? 1
  },
  { immediate: true },
)

// ---------------------------------------------------------------------------
// Debounced config emission
// ---------------------------------------------------------------------------

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function emitConfigUpdate() {
  if (!props.node || props.readOnly) return
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    if (!props.node) return
    emit('update-config', props.node.id, {
      ...localConfig.value,
      error_mode: localErrorMode.value,
      retry_max: localRetryMax.value,
      retry_backoff_seconds: localRetryBackoff.value,
    })
  }, 300)
}

function emitLabelUpdate() {
  if (!props.node || props.readOnly) return
  emit('update-label', props.node.id, localLabel.value)
}

function setConfigField(key: string, value: unknown) {
  localConfig.value = { ...localConfig.value, [key]: value }
  emitConfigUpdate()
}

onUnmounted(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
})

// ---------------------------------------------------------------------------
// Computed helpers
// ---------------------------------------------------------------------------

const nodeType = computed(() => props.node?.type || '')

const nodeTypeLabel = computed(() => {
  const labels: Record<string, string> = {
    trigger: 'Trigger',
    skill: 'Skill',
    command: 'Command',
    agent: 'Agent',
    script: 'Script',
    conditional: 'Conditional',
    transform: 'Transform',
  }
  return labels[nodeType.value] || 'Unknown'
})

const nodeTypeIcon = computed(() => {
  const icons: Record<string, string> = {
    trigger: '\u26A1',
    skill: '\u2728',
    command: '\u2318',
    agent: '\uD83E\uDD16',
    script: '\uD83D\uDCC4',
    conditional: '\u25C7',
    transform: '\u21C4',
  }
  return icons[nodeType.value] || '?'
})

// Dynamic condition_type dependent fields
const showConditionValue = computed(
  () =>
    nodeType.value === 'conditional' &&
    localConfig.value.condition_type === 'contains',
)

// Dynamic transform operation dependent fields
const showFieldPath = computed(
  () =>
    nodeType.value === 'transform' &&
    localConfig.value.operation === 'extract_field',
)

const showTemplate = computed(
  () =>
    nodeType.value === 'transform' && localConfig.value.operation === 'template',
)

// Trigger subtype conditional field visibility
const showCronFields = computed(
  () => nodeType.value === 'trigger' && localConfig.value.trigger_subtype === 'cron',
)
const showPollFields = computed(
  () => nodeType.value === 'trigger' && localConfig.value.trigger_subtype === 'poll',
)
const showFileWatchFields = computed(
  () => nodeType.value === 'trigger' && localConfig.value.trigger_subtype === 'file_watch',
)
const showCompletionFields = computed(
  () => nodeType.value === 'trigger' && localConfig.value.trigger_subtype === 'completion',
)

// Script language-aware placeholder
const scriptPlaceholder = computed(() => {
  const lang = localConfig.value.language || 'shell'
  if (lang === 'python')
    return 'import json\n\n# Your Python script here\nresult = {"status": "ok"}\nprint(json.dumps(result))'
  if (lang === 'node')
    return 'const result = { status: "ok" };\nconsole.log(JSON.stringify(result));'
  return '#!/bin/bash\n\n# Your shell script here\necho "done"'
})

// ---------------------------------------------------------------------------
// Delete node
// ---------------------------------------------------------------------------

function handleDelete() {
  if (!props.node) return
  if (!showDeleteConfirm.value) {
    showDeleteConfirm.value = true
    return
  }
  emit('delete-node', props.node.id)
  showDeleteConfirm.value = false
}
</script>

<template>
  <div class="node-config-panel">
    <!-- Empty state -->
    <div v-if="!node" class="config-empty">
      <div class="empty-icon">
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <circle cx="12" cy="12" r="3" />
          <path
            d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06A1.65 1.65 0 0019.32 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"
          />
        </svg>
      </div>
      <p class="empty-text">Select a node to configure</p>
    </div>

    <!-- Config form -->
    <template v-else>
      <!-- Header -->
      <div class="config-header">
        <div class="header-row">
          <span class="type-badge" :class="nodeType">
            {{ nodeTypeIcon }} {{ nodeTypeLabel }}
          </span>
          <button class="close-btn" title="Close panel" @click="$emit('close')">
            <svg
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <line x1="12" y1="4" x2="4" y2="12" />
              <line x1="4" y1="4" x2="12" y2="12" />
            </svg>
          </button>
        </div>
        <div class="label-field">
          <label class="field-label">Label</label>
          <input
            v-model="localLabel"
            class="field-input"
            type="text"
            placeholder="Node label"
            :disabled="readOnly"
            @input="emitLabelUpdate"
          />
        </div>
      </div>

      <div class="config-divider"></div>

      <!-- Type-specific config fields -->
      <div class="config-body">
        <div class="section-title">Configuration</div>

        <!-- ==================== TRIGGER ==================== -->
        <template v-if="nodeType === 'trigger'">
          <div class="field-group">
            <label class="field-label">Trigger Source</label>
            <select
              class="field-select"
              :value="(localConfig.trigger_id as string) || ''"
              :disabled="readOnly || entitiesLoading"
              @change="onTriggerSelected(($event.target as HTMLSelectElement).value)"
            >
              <option value="">No linked trigger</option>
              <option v-for="t in triggers" :key="t.id" :value="t.id">
                {{ t.name }}
              </option>
            </select>
          </div>
          <div class="field-group">
            <label class="field-label">Trigger Type</label>
            <select
              class="field-select"
              :value="localConfig.trigger_subtype || 'manual'"
              :disabled="readOnly"
              @change="
                setConfigField(
                  'trigger_subtype',
                  ($event.target as HTMLSelectElement).value,
                )
              "
            >
              <option value="manual">Manual</option>
              <option value="cron">Cron Schedule</option>
              <option value="poll">Poll</option>
              <option value="file_watch">File Watch</option>
              <option value="completion">Completion</option>
            </select>
          </div>
          <!-- Cron-specific fields -->
          <template v-if="showCronFields">
            <div class="field-group">
              <label class="field-label">Cron Expression</label>
              <input
                class="field-input"
                type="text"
                placeholder="*/5 * * * *"
                :value="(localConfig.cron_expression as string) || ''"
                :disabled="readOnly"
                @input="setConfigField('cron_expression', ($event.target as HTMLInputElement).value)"
              />
            </div>
            <div class="field-group">
              <label class="field-label">Timezone</label>
              <select
                class="field-select"
                :value="(localConfig.cron_timezone as string) || 'UTC'"
                :disabled="readOnly"
                @change="setConfigField('cron_timezone', ($event.target as HTMLSelectElement).value)"
              >
                <option value="UTC">UTC</option>
                <option value="US/Eastern">US/Eastern</option>
                <option value="US/Pacific">US/Pacific</option>
                <option value="Europe/London">Europe/London</option>
              </select>
            </div>
          </template>
          <!-- Poll-specific fields -->
          <div v-if="showPollFields" class="field-group">
            <label class="field-label">Poll Interval (seconds)</label>
            <input
              class="field-input field-number"
              type="number"
              min="5"
              max="3600"
              :value="(localConfig.poll_interval_seconds as number) || 60"
              :disabled="readOnly"
              @input="setConfigField('poll_interval_seconds', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
          <!-- File watch-specific fields -->
          <div v-if="showFileWatchFields" class="field-group">
            <label class="field-label">Watch Path</label>
            <input
              class="field-input"
              type="text"
              placeholder="/path/to/watch"
              :value="(localConfig.watch_path as string) || ''"
              :disabled="readOnly"
              @input="setConfigField('watch_path', ($event.target as HTMLInputElement).value)"
            />
          </div>
          <!-- Completion-specific fields -->
          <div v-if="showCompletionFields" class="field-group">
            <label class="field-label">Wait For Node ID</label>
            <input
              class="field-input"
              type="text"
              placeholder="node-xxx"
              :value="(localConfig.completion_node_id as string) || ''"
              :disabled="readOnly"
              @input="setConfigField('completion_node_id', ($event.target as HTMLInputElement).value)"
            />
          </div>
        </template>

        <!-- ==================== SKILL ==================== -->
        <template v-if="nodeType === 'skill'">
          <div class="field-group">
            <label class="field-label">Skill</label>
            <select
              class="field-select"
              :value="(localConfig.skill_name as string) || ''"
              :disabled="readOnly || entitiesLoading"
              @change="onSkillSelected(($event.target as HTMLSelectElement).value)"
            >
              <option value="" disabled>Select a skill...</option>
              <option v-for="s in skills" :key="s.name" :value="s.name">
                {{ s.name }}{{ s.description ? ` — ${s.description}` : '' }}
              </option>
            </select>
          </div>
        </template>

        <!-- ==================== COMMAND ==================== -->
        <template v-if="nodeType === 'command'">
          <div class="field-group">
            <label class="field-label">Predefined Command</label>
            <select
              class="field-select"
              :value="(localConfig.command_id as string) || ''"
              :disabled="readOnly || entitiesLoading"
              @change="onCommandSelected(($event.target as HTMLSelectElement).value)"
            >
              <option value="">Custom command...</option>
              <option v-for="c in commands" :key="c.id" :value="String(c.id)">
                {{ c.name }}{{ c.description ? ` — ${c.description}` : '' }}
              </option>
            </select>
          </div>
          <div class="field-group">
            <label class="field-label">Command</label>
            <textarea
              class="field-textarea"
              placeholder="e.g. echo 'hello'"
              rows="3"
              :value="(localConfig.command as string) || ''"
              :disabled="readOnly"
              @input="
                setConfigField(
                  'command',
                  ($event.target as HTMLTextAreaElement).value,
                )
              "
            />
          </div>
          <div class="field-group">
            <label class="field-label">Working Directory</label>
            <input
              class="field-input"
              type="text"
              placeholder="/path/to/dir"
              :value="(localConfig.working_dir as string) || ''"
              :disabled="readOnly"
              @input="
                setConfigField(
                  'working_dir',
                  ($event.target as HTMLInputElement).value,
                )
              "
            />
          </div>
        </template>

        <!-- ==================== AGENT ==================== -->
        <template v-if="nodeType === 'agent'">
          <div class="field-group">
            <label class="field-label">Agent</label>
            <select
              class="field-select"
              :value="(localConfig.agent_id as string) || ''"
              :disabled="readOnly || entitiesLoading"
              @change="onAgentSelected(($event.target as HTMLSelectElement).value)"
            >
              <option value="" disabled>Select an agent...</option>
              <option v-for="a in agents" :key="a.id" :value="a.id">
                {{ a.name }}{{ a.description ? ` — ${a.description}` : '' }}
              </option>
            </select>
          </div>
          <div class="field-group">
            <label class="field-label">Prompt</label>
            <textarea
              class="field-textarea"
              placeholder="Instructions for the agent..."
              rows="4"
              :value="(localConfig.prompt as string) || ''"
              :disabled="readOnly"
              @input="
                setConfigField(
                  'prompt',
                  ($event.target as HTMLTextAreaElement).value,
                )
              "
            />
          </div>
        </template>

        <!-- ==================== SCRIPT ==================== -->
        <template v-if="nodeType === 'script'">
          <div class="field-group">
            <label class="field-label">Language</label>
            <select
              class="field-select"
              :value="localConfig.language || 'shell'"
              :disabled="readOnly"
              @change="
                setConfigField(
                  'language',
                  ($event.target as HTMLSelectElement).value,
                )
              "
            >
              <option value="shell">Shell</option>
              <option value="python">Python</option>
              <option value="node">Node.js</option>
            </select>
          </div>
          <div class="field-group">
            <label class="field-label">Script</label>
            <textarea
              class="field-textarea"
              :placeholder="scriptPlaceholder"
              rows="6"
              :value="(localConfig.script as string) || ''"
              :disabled="readOnly"
              @input="
                setConfigField(
                  'script',
                  ($event.target as HTMLTextAreaElement).value,
                )
              "
            />
          </div>
          <div class="field-group">
            <label class="field-label">Timeout (seconds)</label>
            <input
              class="field-input field-number"
              type="number"
              min="1"
              max="300"
              :value="(localConfig.timeout_seconds as number) || 30"
              :disabled="readOnly"
              @input="setConfigField('timeout_seconds', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </template>

        <!-- ==================== CONDITIONAL ==================== -->
        <template v-if="nodeType === 'conditional'">
          <div class="field-group">
            <label class="field-label">Condition Type</label>
            <select
              class="field-select"
              :value="localConfig.condition_type || ''"
              :disabled="readOnly"
              @change="
                setConfigField(
                  'condition_type',
                  ($event.target as HTMLSelectElement).value,
                )
              "
            >
              <option value="" disabled>Select condition...</option>
              <option value="has_text">Has Text</option>
              <option value="exit_code_zero">Exit Code Zero</option>
              <option value="contains">Contains</option>
            </select>
          </div>
          <div v-if="showConditionValue" class="field-group">
            <label class="field-label">Condition Value</label>
            <input
              class="field-input"
              type="text"
              placeholder="Text to search for..."
              :value="(localConfig.condition_value as string) || ''"
              :disabled="readOnly"
              @input="
                setConfigField(
                  'condition_value',
                  ($event.target as HTMLInputElement).value,
                )
              "
            />
          </div>
          <div class="field-group">
            <label class="field-label">Expression</label>
            <textarea
              class="field-textarea"
              placeholder="e.g. output.status === 'success' && output.data.length > 0"
              rows="3"
              :value="(localConfig.condition_expression as string) || ''"
              :disabled="readOnly"
              @input="setConfigField('condition_expression', ($event.target as HTMLTextAreaElement).value)"
            />
          </div>
          <div class="field-group">
            <label class="field-label">Source Field</label>
            <input
              class="field-input"
              type="text"
              placeholder="e.g. output.status"
              :value="(localConfig.source_field as string) || ''"
              :disabled="readOnly"
              @input="setConfigField('source_field', ($event.target as HTMLInputElement).value)"
            />
          </div>
        </template>

        <!-- ==================== TRANSFORM ==================== -->
        <template v-if="nodeType === 'transform'">
          <div class="field-group">
            <label class="field-label">Operation</label>
            <select
              class="field-select"
              :value="localConfig.operation || ''"
              :disabled="readOnly"
              @change="
                setConfigField(
                  'operation',
                  ($event.target as HTMLSelectElement).value,
                )
              "
            >
              <option value="" disabled>Select operation...</option>
              <option value="extract_field">Extract Field</option>
              <option value="template">Template</option>
              <option value="json_parse">JSON Parse</option>
              <option value="uppercase">Uppercase</option>
              <option value="lowercase">Lowercase</option>
            </select>
          </div>
          <div v-if="showFieldPath" class="field-group">
            <label class="field-label">Field Path</label>
            <input
              class="field-input"
              type="text"
              placeholder="e.g. data.result"
              :value="(localConfig.field_path as string) || ''"
              :disabled="readOnly"
              @input="
                setConfigField(
                  'field_path',
                  ($event.target as HTMLInputElement).value,
                )
              "
            />
          </div>
          <div v-if="showFieldPath" class="field-group">
            <label class="field-label">Default Value</label>
            <input
              class="field-input"
              type="text"
              placeholder="Fallback if field not found"
              :value="(localConfig.default_value as string) || ''"
              :disabled="readOnly"
              @input="setConfigField('default_value', ($event.target as HTMLInputElement).value)"
            />
          </div>
          <div v-if="showTemplate" class="field-group">
            <label class="field-label">Template</label>
            <textarea
              class="field-textarea"
              placeholder="Template string..."
              rows="4"
              :value="(localConfig.template as string) || ''"
              :disabled="readOnly"
              @input="
                setConfigField(
                  'template',
                  ($event.target as HTMLTextAreaElement).value,
                )
              "
            />
          </div>
          <div class="field-group">
            <label class="field-label">Description</label>
            <input
              class="field-input"
              type="text"
              placeholder="What this transform does..."
              :value="(localConfig.description as string) || ''"
              :disabled="readOnly"
              @input="setConfigField('description', ($event.target as HTMLInputElement).value)"
            />
          </div>
        </template>
      </div>

      <div class="config-divider"></div>

      <!-- Error handling section -->
      <div class="config-body">
        <div class="section-title">Error Handling</div>
        <div class="field-group">
          <label class="field-label">Error Mode</label>
          <select
            v-model="localErrorMode"
            class="field-select"
            :disabled="readOnly"
            @change="emitConfigUpdate()"
          >
            <option value="stop">Stop workflow</option>
            <option value="continue">Continue (skip)</option>
            <option value="continue_with_error">Continue with error</option>
          </select>
        </div>
        <div class="field-group">
          <label class="field-label">Max Retries</label>
          <input
            v-model.number="localRetryMax"
            class="field-input field-number"
            type="number"
            min="0"
            max="5"
            :disabled="readOnly"
            @input="emitConfigUpdate()"
          />
        </div>
        <div class="field-group">
          <label class="field-label">Retry Backoff (seconds)</label>
          <input
            v-model.number="localRetryBackoff"
            class="field-input field-number"
            type="number"
            min="1"
            max="60"
            :disabled="readOnly"
            @input="emitConfigUpdate()"
          />
        </div>
      </div>

      <div class="config-divider"></div>

      <!-- Footer: Delete -->
      <div class="config-footer">
        <button
          v-if="!readOnly"
          :class="['delete-btn', { confirm: showDeleteConfirm }]"
          @click="handleDelete"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path
              d="M2 4h12M5.333 4V2.667a1.333 1.333 0 011.334-1.334h2.666a1.333 1.333 0 011.334 1.334V4M12.667 4v9.333a1.333 1.333 0 01-1.334 1.334H4.667a1.333 1.333 0 01-1.334-1.334V4"
            />
          </svg>
          {{ showDeleteConfirm ? 'Click again to confirm' : 'Delete Node' }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.node-config-panel {
  width: 280px;
  background: var(--bg-secondary, #12121a);
  border-left: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  overflow-y: auto;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}

/* Empty state */
.config-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-tertiary, #606070);
  padding: 24px;
}

.empty-icon {
  opacity: 0.4;
}

.empty-text {
  font-size: 13px;
  margin: 0;
  text-align: center;
}

/* Header */
.config-header {
  padding: 16px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.type-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 10px;
  white-space: nowrap;
}

.type-badge.trigger {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}
.type-badge.skill {
  background: rgba(34, 211, 238, 0.15);
  color: #22d3ee;
}
.type-badge.command {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}
.type-badge.agent {
  background: rgba(167, 139, 250, 0.15);
  color: #a78bfa;
}
.type-badge.script {
  background: rgba(167, 139, 250, 0.15);
  color: #a78bfa;
}
.type-badge.conditional {
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
}
.type-badge.transform {
  background: rgba(167, 139, 250, 0.15);
  color: #a78bfa;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-tertiary, #606070);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  transition: color 0.15s;
}

.close-btn:hover {
  color: var(--text-primary, #f0f0f5);
}

/* Config body */
.config-body {
  padding: 12px 16px;
}

.section-title {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary, #606070);
  margin-bottom: 10px;
}

.config-divider {
  height: 1px;
  background: var(--border-subtle, rgba(255, 255, 255, 0.06));
}

/* Form fields */
.field-group {
  margin-bottom: 10px;
}

.field-label {
  display: block;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary, #a0a0b0);
  margin-bottom: 4px;
}

.label-field {
  display: flex;
  flex-direction: column;
}

.field-input,
.field-select,
.field-textarea {
  width: 100%;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #f0f0f5);
  font-size: 12px;
  font-family: inherit;
  transition:
    border-color 0.15s,
    background 0.15s;
  box-sizing: border-box;
}

.field-input:focus,
.field-select:focus,
.field-textarea:focus {
  outline: none;
  border-color: var(--accent-cyan, #00d4ff);
  background: var(--bg-elevated, #222230);
}

.field-input:disabled,
.field-select:disabled,
.field-textarea:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.field-textarea {
  resize: vertical;
  min-height: 60px;
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  line-height: 1.5;
}

.field-select {
  cursor: pointer;
}

.field-number {
  width: 100px;
}

/* Footer */
.config-footer {
  padding: 12px 16px;
  margin-top: auto;
}

.delete-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.2);
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  transition:
    background 0.15s,
    border-color 0.15s;
  justify-content: center;
}

.delete-btn:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.4);
}

.delete-btn.confirm {
  background: rgba(239, 68, 68, 0.25);
  border-color: #ef4444;
  font-weight: 600;
}
</style>
