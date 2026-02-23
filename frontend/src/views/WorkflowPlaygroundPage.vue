<script setup lang="ts">
import { ref, nextTick, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import type { ConversationMessage } from '../services/api';
import { workflowApi, superAgentApi, superAgentSessionApi } from '../services/api';
import AiChatPanel from '../components/ai/AiChatPanel.vue';
import WorkflowCanvas from '../components/workflow/WorkflowCanvas.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();

const showToast = useToast();

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const messages = ref<ConversationMessage[]>([]);
const isProcessing = ref(false);
const streamingContent = ref('');
const inputMessage = ref('');
const previewWorkflowId = ref<string | null>(null);
const generatedWorkflowId = ref<string | null>(null);

// Real AI backend state
const isDemoMode = ref(true);

useWebMcpTool({
  name: 'agented_workflow_playground_get_state',
  description: 'Returns the current state of the Workflow Playground page',
  page: 'WorkflowPlaygroundPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'WorkflowPlaygroundPage',
        messageCount: messages.value.length,
        isProcessing: isProcessing.value,
        previewWorkflowId: previewWorkflowId.value,
        isDemoMode: isDemoMode.value,
      }),
    }],
  }),
  deps: [messages, isProcessing, previewWorkflowId, isDemoMode],
});
const aiSuperAgentId = ref<string | null>(null);
const aiSessionId = ref<string | null>(null);
const selectedBackend = ref('auto');
const selectedAccountId = ref<string | null>(null);
const selectedModel = ref<string | null>(null);
let chatEventSource: EventSource | null = null;

// Chat panel configuration
const assistantIconPaths = [
  'M12 2L2 7l10 5 10-5-10-5z',
  'M2 17l10 5 10-5',
  'M2 12l10 5 10-5',
];

// ---------------------------------------------------------------------------
// Real AI Backend Discovery
// ---------------------------------------------------------------------------

async function discoverAiBackend() {
  try {
    const result = await superAgentApi.list();
    const agents = result.super_agents || [];
    if (agents.length > 0) {
      // Use the first available SuperAgent for workflow AI
      aiSuperAgentId.value = agents[0].id;
      // Create a session
      const sess = await superAgentSessionApi.create(agents[0].id);
      aiSessionId.value = sess.session_id;
      isDemoMode.value = false;
      // Connect SSE
      connectChatStream();
    }
  } catch {
    // No AI backend available, stay in demo mode
    isDemoMode.value = true;
  }
}

function connectChatStream() {
  if (!aiSuperAgentId.value || !aiSessionId.value) return;
  chatEventSource = superAgentSessionApi.chatStream(aiSuperAgentId.value, aiSessionId.value);

  let accumulatedContent = '';

  chatEventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'state_delta' && data.delta?.content) {
        accumulatedContent += data.delta.content;
        streamingContent.value = accumulatedContent;
      } else if (data.type === 'finish' || data.type === 'done') {
        // Final content
        const finalContent = accumulatedContent || streamingContent.value;
        if (finalContent) {
          messages.value.push({
            role: 'assistant',
            content: finalContent,
            timestamp: new Date().toISOString(),
          });
          // Check for JSON graph in the response
          const jsonMatch = finalContent.match(/```json\n([\s\S]*?)\n```/);
          if (jsonMatch) {
            tryCreateWorkflowFromJson(jsonMatch[1]);
          }
        }
        streamingContent.value = '';
        accumulatedContent = '';
        isProcessing.value = false;
      } else if (data.type === 'error') {
        isProcessing.value = false;
        streamingContent.value = '';
        accumulatedContent = '';
        showToast(data.error || 'AI backend error', 'error');
      }
    } catch {
      // Ignore parse errors for heartbeat events
    }
  };

  chatEventSource.onerror = () => {
    // SSE error -- fall back to demo mode gracefully
    if (isProcessing.value) {
      isProcessing.value = false;
      streamingContent.value = '';
    }
  };
}

// Cleanup SSE on unmount
onUnmounted(() => {
  if (chatEventSource) {
    chatEventSource.close();
    chatEventSource = null;
  }
});

// Try to discover AI backend on mount (non-blocking)
discoverAiBackend();

// ---------------------------------------------------------------------------
// Message Handling
// ---------------------------------------------------------------------------

function handleSend() {
  if (!inputMessage.value.trim()) return;
  const userMsg = inputMessage.value.trim();
  inputMessage.value = '';

  // Add user message
  messages.value.push({
    role: 'user',
    content: userMsg,
    timestamp: new Date().toISOString(),
  });

  isProcessing.value = true;

  if (!isDemoMode.value && aiSuperAgentId.value && aiSessionId.value) {
    // Send via real AI backend
    superAgentSessionApi
      .sendChatMessage(aiSuperAgentId.value, aiSessionId.value, userMsg)
      .catch(() => {
        // If real AI fails, fall back to stub
        isProcessing.value = false;
        showToast('AI backend unavailable, using demo mode', 'info');
        isDemoMode.value = true;
        handleStubResponse(userMsg);
      });
  } else {
    // Use stub response
    handleStubResponse(userMsg);
  }
}

function handleStubResponse(userMsg: string) {
  isProcessing.value = true;
  setTimeout(() => {
    const response = generateStubResponse(userMsg);
    messages.value.push({
      role: 'assistant',
      content: response,
      timestamp: new Date().toISOString(),
    });
    isProcessing.value = false;

    // Check if response contains a JSON code block and try to create workflow
    const jsonMatch = response.match(/```json\n([\s\S]*?)\n```/);
    if (jsonMatch) {
      tryCreateWorkflowFromJson(jsonMatch[1]);
    }
  }, 800);
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
}

// ---------------------------------------------------------------------------
// Stub AI Response Generator
// ---------------------------------------------------------------------------

function generateStubResponse(userMessage: string): string {
  const lower = userMessage.toLowerCase();

  // If the user mentions specific workflow patterns, generate a template
  if (lower.includes('deploy') || lower.includes('ci') || lower.includes('build')) {
    return generateDeployWorkflowResponse();
  }
  if (lower.includes('review') || lower.includes('pr') || lower.includes('code')) {
    return generateReviewWorkflowResponse();
  }
  if (lower.includes('data') || lower.includes('etl') || lower.includes('transform')) {
    return generateDataWorkflowResponse();
  }
  if (lower.includes('monitor') || lower.includes('alert') || lower.includes('check')) {
    return generateMonitorWorkflowResponse();
  }

  // Generic response for unrecognized patterns
  return `I can help you design a workflow! Here are some things I can create:

- **Deploy Pipeline** - trigger -> build -> test -> deploy with conditional rollback
- **Code Review** - trigger -> analyze code -> run tests -> generate report
- **Data Pipeline** - trigger -> extract data -> transform -> load
- **Monitoring** - trigger -> health check -> conditional alert

Describe what your workflow should do and I'll generate the graph for you.`;
}

function generateDeployWorkflowResponse(): string {
  const graph = {
    nodes: [
      { id: 'trigger-1', type: 'trigger', label: 'Deploy Trigger', config: { trigger_subtype: 'manual' }, error_mode: 'stop', retry_max: 0, retry_backoff_seconds: 1 },
      { id: 'command-1', type: 'command', label: 'Run Build', config: { command: 'npm run build' }, error_mode: 'stop', retry_max: 2, retry_backoff_seconds: 5 },
      { id: 'command-2', type: 'command', label: 'Run Tests', config: { command: 'npm test' }, error_mode: 'stop', retry_max: 1, retry_backoff_seconds: 3 },
      { id: 'conditional-1', type: 'conditional', label: 'Tests Passed?', config: { condition: 'exit_code == 0' }, error_mode: 'stop', retry_max: 0, retry_backoff_seconds: 1 },
      { id: 'script-1', type: 'script', label: 'Deploy to Production', config: { script_path: './deploy.sh' }, error_mode: 'continue_with_error', retry_max: 1, retry_backoff_seconds: 10 },
      { id: 'agent-1', type: 'agent', label: 'Notify Team', config: { agent_id: '' }, error_mode: 'continue', retry_max: 0, retry_backoff_seconds: 1 },
    ],
    edges: [
      { source: 'trigger-1', target: 'command-1' },
      { source: 'command-1', target: 'command-2' },
      { source: 'command-2', target: 'conditional-1' },
      { source: 'conditional-1', target: 'script-1' },
      { source: 'script-1', target: 'agent-1' },
    ],
    settings: {},
  };

  return `Here's a deploy pipeline workflow for you:

\`\`\`json
${JSON.stringify(graph, null, 2)}
\`\`\`

This workflow:
1. **Trigger** - starts manually (you can change to cron or webhook)
2. **Run Build** - executes the build command with 2 retries
3. **Run Tests** - validates the build
4. **Tests Passed?** - conditional check on test results
5. **Deploy** - deploys to production with error continuation
6. **Notify Team** - sends notification via an agent

The workflow has been loaded into the preview canvas. Click "Open in Builder" to customize it further.`;
}

function generateReviewWorkflowResponse(): string {
  const graph = {
    nodes: [
      { id: 'trigger-1', type: 'trigger', label: 'PR Opened', config: { trigger_subtype: 'manual' }, error_mode: 'stop', retry_max: 0, retry_backoff_seconds: 1 },
      { id: 'agent-1', type: 'agent', label: 'Analyze Code', config: { agent_id: '' }, error_mode: 'stop', retry_max: 1, retry_backoff_seconds: 5 },
      { id: 'command-1', type: 'command', label: 'Run Linter', config: { command: 'npm run lint' }, error_mode: 'continue', retry_max: 0, retry_backoff_seconds: 1 },
      { id: 'transform-1', type: 'transform', label: 'Aggregate Results', config: { mapping: 'merge_reports' }, error_mode: 'stop', retry_max: 0, retry_backoff_seconds: 1 },
      { id: 'agent-2', type: 'agent', label: 'Generate Review', config: { agent_id: '' }, error_mode: 'stop', retry_max: 1, retry_backoff_seconds: 5 },
    ],
    edges: [
      { source: 'trigger-1', target: 'agent-1' },
      { source: 'trigger-1', target: 'command-1' },
      { source: 'agent-1', target: 'transform-1' },
      { source: 'command-1', target: 'transform-1' },
      { source: 'transform-1', target: 'agent-2' },
    ],
    settings: {},
  };

  return `Here's a code review workflow:

\`\`\`json
${JSON.stringify(graph, null, 2)}
\`\`\`

This workflow:
1. **PR Opened** - triggers when a pull request is created
2. **Analyze Code** (parallel) - AI agent analyzes the code changes
3. **Run Linter** (parallel) - static analysis runs alongside
4. **Aggregate Results** - combines both analysis outputs
5. **Generate Review** - AI generates a comprehensive review comment

Click "Open in Builder" to customize the agents and commands.`;
}

function generateDataWorkflowResponse(): string {
  const graph = {
    nodes: [
      { id: 'trigger-1', type: 'trigger', label: 'Schedule', config: { trigger_subtype: 'cron' }, error_mode: 'stop', retry_max: 0, retry_backoff_seconds: 1 },
      { id: 'script-1', type: 'script', label: 'Extract Data', config: { script_path: './extract.py' }, error_mode: 'stop', retry_max: 3, retry_backoff_seconds: 10 },
      { id: 'transform-1', type: 'transform', label: 'Clean & Transform', config: { mapping: 'normalize' }, error_mode: 'stop', retry_max: 1, retry_backoff_seconds: 5 },
      { id: 'script-2', type: 'script', label: 'Load to DB', config: { script_path: './load.py' }, error_mode: 'stop', retry_max: 2, retry_backoff_seconds: 10 },
    ],
    edges: [
      { source: 'trigger-1', target: 'script-1' },
      { source: 'script-1', target: 'transform-1' },
      { source: 'transform-1', target: 'script-2' },
    ],
    settings: {},
  };

  return `Here's a data pipeline (ETL) workflow:

\`\`\`json
${JSON.stringify(graph, null, 2)}
\`\`\`

This workflow:
1. **Schedule** - runs on a cron schedule
2. **Extract Data** - pulls data from source with 3 retries
3. **Clean & Transform** - normalizes and transforms the data
4. **Load to DB** - writes transformed data to the database

Click "Open in Builder" to configure the scripts and schedule.`;
}

function generateMonitorWorkflowResponse(): string {
  const graph = {
    nodes: [
      { id: 'trigger-1', type: 'trigger', label: 'Health Check Timer', config: { trigger_subtype: 'cron' }, error_mode: 'stop', retry_max: 0, retry_backoff_seconds: 1 },
      { id: 'command-1', type: 'command', label: 'Check Services', config: { command: 'curl -s http://api/health' }, error_mode: 'continue', retry_max: 2, retry_backoff_seconds: 5 },
      { id: 'conditional-1', type: 'conditional', label: 'All Healthy?', config: { condition: 'status == ok' }, error_mode: 'stop', retry_max: 0, retry_backoff_seconds: 1 },
      { id: 'agent-1', type: 'agent', label: 'Send Alert', config: { agent_id: '' }, error_mode: 'stop', retry_max: 1, retry_backoff_seconds: 5 },
    ],
    edges: [
      { source: 'trigger-1', target: 'command-1' },
      { source: 'command-1', target: 'conditional-1' },
      { source: 'conditional-1', target: 'agent-1' },
    ],
    settings: {},
  };

  return `Here's a monitoring workflow:

\`\`\`json
${JSON.stringify(graph, null, 2)}
\`\`\`

This workflow:
1. **Health Check Timer** - runs periodically via cron
2. **Check Services** - pings the health endpoint with retries
3. **All Healthy?** - evaluates the health response
4. **Send Alert** - notifies the team if services are unhealthy

Click "Open in Builder" to set the cron schedule and alert configuration.`;
}

// ---------------------------------------------------------------------------
// Workflow Creation from JSON
// ---------------------------------------------------------------------------

async function tryCreateWorkflowFromJson(jsonStr: string) {
  try {
    const graph = JSON.parse(jsonStr);

    // Validate basic structure
    if (!graph.nodes || !Array.isArray(graph.nodes)) return;
    if (!graph.edges || !Array.isArray(graph.edges)) return;

    // Create workflow
    const result = await workflowApi.create({
      name: `AI-Generated Workflow ${new Date().toLocaleTimeString()}`,
      description: 'Generated by AI Workflow Playground',
      trigger_type: 'manual',
    });

    // Create a version with the graph
    await workflowApi.createVersion(result.workflow_id, {
      graph_json: JSON.stringify(graph),
    });

    generatedWorkflowId.value = result.workflow_id;
    previewWorkflowId.value = result.workflow_id;

    await nextTick();
    showToast('Workflow generated and loaded into preview', 'success');
  } catch {
    showToast('Failed to create workflow from generated JSON', 'error');
  }
}

// ---------------------------------------------------------------------------
// Navigation to Builder
// ---------------------------------------------------------------------------

function openInBuilder() {
  if (!generatedWorkflowId.value) return;
  router.push({ name: 'workflow-builder', params: { workflowId: generatedWorkflowId.value } });
}
</script>

<template>
  <div class="workflow-playground-page">
    <!-- Header -->
    <div class="playground-header">
      <div class="header-title">
        <h1>Workflow Playground</h1>
        <p>Describe a workflow and the AI will generate it for you</p>
      </div>
      <div v-if="isDemoMode" class="demo-badge">
        Demo mode — connect an AI backend for real assistance
      </div>
      <div class="header-actions">
        <button
          v-if="generatedWorkflowId"
          class="btn btn-primary"
          @click="openInBuilder"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
          Open in Builder
        </button>
      </div>
    </div>

    <!-- Main content: two-column layout -->
    <div class="playground-content">
      <!-- Left panel: Chat UI -->
      <div class="left-panel">
        <AiChatPanel
          :messages="messages"
          :isProcessing="isProcessing"
          :streamingContent="streamingContent"
          :inputMessage="inputMessage"
          :conversationId="null"
          :canFinalize="false"
          :isFinalizing="false"
          :assistantIconPaths="assistantIconPaths"
          inputPlaceholder="Describe your workflow... e.g., 'Create a deploy pipeline with build, test, and notification'"
          entityLabel="Workflow"
          bannerTitle=""
          bannerButtonLabel=""
          :showBackendSelector="true"
          :selected-backend="selectedBackend"
          :selected-account-id="selectedAccountId"
          :selected-model="selectedModel"
          @update:inputMessage="inputMessage = $event"
          @update:selected-backend="selectedBackend = $event"
          @update:selected-account-id="selectedAccountId = $event"
          @update:selected-model="selectedModel = $event"
          @send="handleSend"
          @keydown="handleKeyDown"
        >
          <template #welcome>
            <div class="wf-welcome">
              <div class="welcome-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="8" y="2" width="8" height="5" rx="1"/>
                  <rect x="8" y="10" width="8" height="5" rx="1"/>
                  <rect x="8" y="18" width="8" height="5" rx="1"/>
                  <line x1="12" y1="7" x2="12" y2="10"/>
                  <line x1="12" y1="15" x2="12" y2="18"/>
                </svg>
              </div>
              <h2>AI Workflow Designer</h2>
              <p>Describe the workflow you want to create, and I'll generate the graph for you. Try:</p>
              <ul class="suggestions">
                <li>"Create a deploy pipeline with build, test, and deploy steps"</li>
                <li>"Build a code review workflow for pull requests"</li>
                <li>"Design a data ETL pipeline with extraction and transformation"</li>
                <li>"Set up a monitoring workflow with health checks and alerts"</li>
              </ul>
            </div>
          </template>
        </AiChatPanel>
      </div>

      <!-- Right panel: Canvas preview -->
      <div class="right-panel">
        <div v-if="!previewWorkflowId" class="preview-placeholder">
          <div class="placeholder-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2"/>
              <rect x="8" y="6" width="8" height="4" rx="1"/>
              <rect x="8" y="14" width="8" height="4" rx="1"/>
              <line x1="12" y1="10" x2="12" y2="14"/>
            </svg>
          </div>
          <h3>Canvas Preview</h3>
          <p>Describe your workflow in the chat and I'll generate it for you. The visual graph will appear here.</p>
        </div>
        <WorkflowCanvas
          v-else
          :workflow-id="previewWorkflowId"
          :read-only="true"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.workflow-playground-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

/* Header */
.playground-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.header-title {
  flex: 1;
  min-width: 0;
}

.header-title h1 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-title p {
  margin: 2px 0 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.demo-badge {
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 500;
  background: rgba(255, 187, 0, 0.1);
  border: 1px solid rgba(255, 187, 0, 0.3);
  border-radius: 4px;
  color: #ffbb00;
  white-space: nowrap;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* Main content */
.playground-content {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.left-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
}

.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--border-default);
  min-height: 0;
  min-width: 0;
}

/* Welcome screen */
.wf-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.welcome-icon {
  width: 64px;
  height: 64px;
  background: var(--bg-tertiary);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
}

.welcome-icon svg {
  width: 32px;
  height: 32px;
  color: var(--accent-cyan);
}

.wf-welcome h2 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: var(--text-primary);
}

.wf-welcome p {
  margin: 0 0 16px 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.suggestions {
  list-style: none;
  padding: 0;
  margin: 0;
  text-align: left;
}

.suggestions li {
  padding: 8px 12px;
  margin: 4px 0;
  background: var(--bg-tertiary);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: default;
}

/* Preview placeholder */
.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px;
  text-align: center;
}

.placeholder-icon {
  width: 80px;
  height: 80px;
  background: var(--bg-tertiary);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
}

.placeholder-icon svg {
  width: 40px;
  height: 40px;
  color: var(--text-tertiary);
}

.preview-placeholder h3 {
  margin: 0 0 8px 0;
  font-size: 16px;
  color: var(--text-primary);
}

.preview-placeholder p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
  max-width: 300px;
}
</style>
