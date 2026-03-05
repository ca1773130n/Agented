<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
const router = useRouter();

interface ExecutionFrame {
  index: number;
  timestamp: string;
  type: 'trigger' | 'context' | 'prompt' | 'api_call' | 'response' | 'output' | 'complete';
  label: string;
  content: string;
  durationMs?: number;
  tokenCount?: number;
}

const frames: ExecutionFrame[] = [
  { index: 0, timestamp: '14:22:00.000', type: 'trigger', label: 'Trigger Received', content: '{"action":"opened","pull_request":{"number":42,"title":"Add OAuth flow"},"repository":{"full_name":"org/api"}}', durationMs: 0 },
  { index: 1, timestamp: '14:22:00.012', type: 'context', label: 'Context Injected', content: 'Fetched 3 changed files (214 lines total):\n- src/auth/oauth.ts (+180, -0)\n- src/middleware/session.ts (+22, -8)\n- src/routes/callback.ts (+12, -4)\n\nRecent git history: 5 commits from last 7 days.', durationMs: 12 },
  { index: 2, timestamp: '14:22:00.024', type: 'prompt', label: 'Final Prompt Built', content: 'You are a senior software engineer conducting a code review.\n\nReview PR #42 "Add OAuth flow" in org/api.\n\nChanged files:\n[...214 lines of diff]\n\nAnalyze for security vulnerabilities, logic errors, performance issues.', durationMs: 12, tokenCount: 4240 },
  { index: 3, timestamp: '14:22:00.042', type: 'api_call', label: 'API Call Sent', content: 'POST claude-opus-4-6 with 4,240 tokens\nMax output: 2048 tokens\nTemperature: 0.1', durationMs: 18 },
  { index: 4, timestamp: '14:22:00.862', type: 'response', label: 'Model Response Received', content: '## Security Analysis\n\nFound 1 high-severity issue:\n**CSRF Vulnerability**: OAuth callback at `/auth/callback` does not validate the `state` parameter...\n\n## Code Quality\n\nThe `handleCallback` function at 87 lines violates single-responsibility...', durationMs: 820, tokenCount: 680 },
  { index: 5, timestamp: '14:22:00.880', type: 'output', label: 'Output Formatted', content: 'Structured output: 3 findings (1 critical, 1 warning, 1 info)\nFormatted for GitHub PR comment', durationMs: 18 },
  { index: 6, timestamp: '14:22:00.900', type: 'complete', label: 'Execution Complete', content: 'Total duration: 888ms\nInput tokens: 4,240 | Output tokens: 680\nEstimated cost: $0.078\nStatus: SUCCESS', durationMs: 20 },
];

const executions = ref([
  { id: 'exec-001', botName: 'bot-pr-review', runAt: '14:22:00', status: 'success' },
  { id: 'exec-002', botName: 'bot-security', runAt: '13:10:00', status: 'failed' },
]);

const selectedExecId = ref('exec-001');
const currentFrame = ref(0);
const isPlaying = ref(false);
const playInterval = ref<ReturnType<typeof setInterval> | null>(null);

const currentFrameData = computed(() => frames[currentFrame.value]);
const progress = computed(() => ((currentFrame.value) / (frames.length - 1)) * 100);

function goTo(idx: number) {
  currentFrame.value = Math.max(0, Math.min(frames.length - 1, idx));
}

function togglePlay() {
  if (isPlaying.value) {
    if (playInterval.value) clearInterval(playInterval.value);
    isPlaying.value = false;
  } else {
    if (currentFrame.value === frames.length - 1) currentFrame.value = 0;
    isPlaying.value = true;
    playInterval.value = setInterval(() => {
      if (currentFrame.value >= frames.length - 1) {
        if (playInterval.value) clearInterval(playInterval.value);
        isPlaying.value = false;
      } else {
        currentFrame.value++;
      }
    }, 600);
  }
}

function frameTypeColor(type: ExecutionFrame['type']) {
  const colors: Record<ExecutionFrame['type'], string> = {
    trigger: 'var(--accent-cyan)',
    context: '#a78bfa',
    prompt: '#fbbf24',
    api_call: '#f59e0b',
    response: '#34d399',
    output: '#60a5fa',
    complete: '#34d399',
  };
  return colors[type] || 'var(--text-muted)';
}
</script>

<template>
  <div class="time-travel">
    <AppBreadcrumb :items="[
      { label: 'Executions', action: () => router.push({ name: 'execution-history' }) },
      { label: 'Time-Travel Debugger' },
    ]" />

    <PageHeader
      title="Execution Time-Travel Debugger"
      subtitle="Step through a recorded execution frame by frame, inspecting prompts, context, and model responses at each stage."
    />

    <div class="layout">
      <!-- Execution selector -->
      <aside class="sidebar card">
        <div class="sidebar-header">Executions</div>
        <div
          v-for="e in executions"
          :key="e.id"
          class="exec-item"
          :class="{ active: selectedExecId === e.id }"
          @click="selectedExecId = e.id; currentFrame = 0; isPlaying = false;"
        >
          <div class="exec-bot">{{ e.botName }}</div>
          <div class="exec-meta">{{ e.runAt }} · <span :class="['exec-status', `es-${e.status}`]">{{ e.status }}</span></div>
        </div>

        <div class="frames-nav">
          <div class="frames-header">Frames ({{ frames.length }})</div>
          <div
            v-for="f in frames"
            :key="f.index"
            class="frame-nav-item"
            :class="{ active: currentFrame === f.index }"
            @click="goTo(f.index)"
          >
            <span class="frame-type-dot" :style="{ background: frameTypeColor(f.type) }"></span>
            <span class="frame-label">{{ f.label }}</span>
          </div>
        </div>
      </aside>

      <!-- Debugger panel -->
      <div class="debugger-main">
        <!-- Progress bar -->
        <div class="card progress-card">
          <div class="progress-controls">
            <button class="ctrl-btn" :disabled="currentFrame === 0" @click="goTo(0)">⏮</button>
            <button class="ctrl-btn" :disabled="currentFrame === 0" @click="goTo(currentFrame - 1)">◀</button>
            <button class="ctrl-btn play-btn" @click="togglePlay">{{ isPlaying ? '⏸' : '▶' }}</button>
            <button class="ctrl-btn" :disabled="currentFrame === frames.length - 1" @click="goTo(currentFrame + 1)">▶</button>
            <button class="ctrl-btn" :disabled="currentFrame === frames.length - 1" @click="goTo(frames.length - 1)">⏭</button>
          </div>
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: `${progress}%` }"></div>
            <div
              v-for="f in frames"
              :key="f.index"
              class="progress-marker"
              :style="{ left: `${(f.index / (frames.length - 1)) * 100}%`, background: frameTypeColor(f.type) }"
              @click="goTo(f.index)"
            ></div>
          </div>
          <div class="progress-meta">
            Frame {{ currentFrame + 1 }} / {{ frames.length }} · {{ currentFrameData.timestamp }}
          </div>
        </div>

        <!-- Current frame content -->
        <div class="card frame-card">
          <div class="frame-header">
            <span class="frame-type-pill" :style="{ background: `${frameTypeColor(currentFrameData.type)}18`, color: frameTypeColor(currentFrameData.type) }">{{ currentFrameData.type.replace('_', ' ') }}</span>
            <span class="frame-label-big">{{ currentFrameData.label }}</span>
            <div class="frame-metrics">
              <span v-if="currentFrameData.durationMs !== undefined" class="frame-metric">+{{ currentFrameData.durationMs }}ms</span>
              <span v-if="currentFrameData.tokenCount" class="frame-metric">{{ currentFrameData.tokenCount.toLocaleString() }} tokens</span>
            </div>
          </div>
          <pre class="frame-content">{{ currentFrameData.content }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.time-travel { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 240px 1fr; gap: 20px; align-items: start; }
.debugger-main { display: flex; flex-direction: column; gap: 14px; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.sidebar-header { padding: 12px 16px; border-bottom: 1px solid var(--border-default); font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); }

.exec-item { padding: 10px 16px; cursor: pointer; border-bottom: 1px solid var(--border-subtle); transition: background 0.1s; }
.exec-item:hover { background: var(--bg-tertiary); }
.exec-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.exec-bot { font-size: 0.8rem; font-weight: 600; color: var(--text-primary); margin-bottom: 2px; }
.exec-meta { font-size: 0.7rem; color: var(--text-muted); }
.exec-status { font-weight: 600; }
.es-success { color: #34d399; }
.es-failed { color: #ef4444; }

.frames-nav { }
.frames-header { padding: 10px 16px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); border-top: 1px solid var(--border-default); border-bottom: 1px solid var(--border-default); }
.frame-nav-item { display: flex; align-items: center; gap: 8px; padding: 8px 16px; cursor: pointer; border-bottom: 1px solid var(--border-subtle); transition: background 0.1s; }
.frame-nav-item:hover { background: var(--bg-tertiary); }
.frame-nav-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.frame-nav-item:last-child { border-bottom: none; }
.frame-type-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.frame-label { font-size: 0.74rem; color: var(--text-secondary); }

.progress-card { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.progress-controls { display: flex; align-items: center; gap: 8px; justify-content: center; }
.ctrl-btn { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); width: 34px; height: 34px; border-radius: 6px; cursor: pointer; font-size: 0.9rem; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
.ctrl-btn:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.ctrl-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.play-btn { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); width: 40px; height: 40px; font-size: 1rem; }
.play-btn:hover { opacity: 0.85; }

.progress-track { position: relative; height: 8px; background: var(--bg-tertiary); border-radius: 4px; cursor: pointer; }
.progress-fill { height: 100%; background: var(--accent-cyan); border-radius: 4px; transition: width 0.3s ease; }
.progress-marker { position: absolute; top: -3px; width: 14px; height: 14px; border-radius: 50%; transform: translateX(-50%); cursor: pointer; border: 2px solid var(--bg-secondary); transition: transform 0.1s; }
.progress-marker:hover { transform: translateX(-50%) scale(1.3); }
.progress-meta { font-size: 0.72rem; color: var(--text-muted); text-align: center; }

.frame-header { display: flex; align-items: center; gap: 10px; padding: 14px 18px; border-bottom: 1px solid var(--border-default); flex-wrap: wrap; }
.frame-type-pill { font-size: 0.72rem; font-weight: 700; padding: 3px 9px; border-radius: 4px; text-transform: capitalize; }
.frame-label-big { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); flex: 1; }
.frame-metrics { display: flex; gap: 10px; }
.frame-metric { font-size: 0.72rem; color: var(--text-muted); background: var(--bg-tertiary); padding: 2px 8px; border-radius: 3px; }

.frame-content { padding: 18px; font-family: 'Geist Mono', monospace; font-size: 0.78rem; color: var(--text-secondary); white-space: pre-wrap; line-height: 1.6; margin: 0; overflow: auto; max-height: 400px; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
