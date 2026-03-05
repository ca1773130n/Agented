<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface OutputSegment {
  id: string;
  text: string;
  comment?: string;
  rating?: 1 | -1;
}

interface AnnotatedExecution {
  id: string;
  botName: string;
  runAt: string;
  qualityScore: number | null;
  rating?: 1 | -1;
  segments: OutputSegment[];
}

const executions = ref<AnnotatedExecution[]>([
  {
    id: 'exec-ann-001',
    botName: 'bot-pr-review',
    runAt: '2026-03-06T14:22:00Z',
    qualityScore: 8.5,
    rating: 1,
    segments: [
      { id: 's1', text: '## Security Analysis\n\nFound 1 potential vulnerability: The `state` parameter in the OAuth callback is not validated, which could allow CSRF attacks.', rating: 1, comment: 'Very accurate finding, exactly what we needed.' },
      { id: 's2', text: '## Code Quality\n\nThe function `handleCallback` is 87 lines long and handles authentication, session creation, and redirect logic. Consider extracting into smaller, single-responsibility functions.', rating: 1 },
      { id: 's3', text: '## Performance\n\nNo major performance issues detected. Database queries in auth flow appear optimized with appropriate indexing.', rating: -1, comment: 'Wrong — we have N+1 queries on user groups lookup.' },
    ],
  },
]);

const selected = ref<AnnotatedExecution>(executions.value[0]);
const isSubmittingRating = ref(false);
const newComment = ref('');
const commentingSegment = ref<string | null>(null);

async function rateExecution(rating: 1 | -1) {
  isSubmittingRating.value = true;
  try {
    await new Promise(r => setTimeout(r, 400));
    selected.value.rating = rating;
    showToast(rating === 1 ? 'Rated thumbs up' : 'Rated thumbs down', 'success');
  } finally {
    isSubmittingRating.value = false;
  }
}

async function rateSegment(seg: OutputSegment, rating: 1 | -1) {
  seg.rating = seg.rating === rating ? undefined : rating;
  await new Promise(r => setTimeout(r, 200));
}

async function addComment(seg: OutputSegment) {
  if (!newComment.value.trim()) return;
  seg.comment = newComment.value;
  newComment.value = '';
  commentingSegment.value = null;
  showToast('Comment saved', 'success');
}

function formatDate(ts: string) {
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const aggStats = computed(() => {
  const all = executions.value;
  const rated = all.filter(e => e.rating !== undefined);
  const positive = rated.filter(e => e.rating === 1).length;
  return { total: all.length, rated: rated.length, positive, negative: rated.length - positive };
});
</script>

<template>
  <div class="exec-annotation">
    <AppBreadcrumb :items="[
      { label: 'Executions', action: () => router.push({ name: 'execution-history' }) },
      { label: 'Annotation & Feedback' },
    ]" />

    <PageHeader
      title="Execution Annotation & Quality Feedback"
      subtitle="Rate executions and leave inline comments on output segments to build a quality signal over time."
    />

    <div class="stats-row">
      <div class="stat-chip card">
        <div class="stat-num">{{ aggStats.total }}</div>
        <div class="stat-label">Total executions</div>
      </div>
      <div class="stat-chip card">
        <div class="stat-num">{{ aggStats.rated }}</div>
        <div class="stat-label">Rated</div>
      </div>
      <div class="stat-chip card">
        <div class="stat-num" style="color: #34d399;">{{ aggStats.positive }}</div>
        <div class="stat-label">Thumbs up</div>
      </div>
      <div class="stat-chip card">
        <div class="stat-num" style="color: #ef4444;">{{ aggStats.negative }}</div>
        <div class="stat-label">Thumbs down</div>
      </div>
    </div>

    <div class="layout">
      <!-- Execution list -->
      <aside class="sidebar">
        <div
          v-for="e in executions"
          :key="e.id"
          class="exec-item card"
          :class="{ active: selected.id === e.id }"
          @click="selected = e"
        >
          <div class="exec-top">
            <span class="exec-bot">{{ e.botName }}</span>
            <span v-if="e.rating === 1" class="thumb thumb-up">👍</span>
            <span v-else-if="e.rating === -1" class="thumb thumb-down">👎</span>
          </div>
          <div class="exec-date">{{ formatDate(e.runAt) }}</div>
          <div v-if="e.qualityScore" class="exec-score">Quality: {{ e.qualityScore }}/10</div>
        </div>
      </aside>

      <!-- Annotation panel -->
      <main class="annotation-main">
        <div class="card exec-header-card">
          <div class="exec-header-content">
            <div>
              <div class="exec-title">{{ selected.botName }} — {{ selected.id }}</div>
              <div class="exec-time">{{ formatDate(selected.runAt) }}</div>
            </div>
            <div class="overall-rating">
              <span class="rating-label">Overall:</span>
              <button
                :class="['rate-btn', { active: selected.rating === 1 }]"
                :disabled="isSubmittingRating"
                @click="rateExecution(1)"
              >👍</button>
              <button
                :class="['rate-btn', { active: selected.rating === -1 }]"
                :disabled="isSubmittingRating"
                @click="rateExecution(-1)"
              >👎</button>
            </div>
          </div>
        </div>

        <div class="segments-list">
          <div v-for="seg in selected.segments" :key="seg.id" class="segment-card card">
            <div class="segment-text">{{ seg.text }}</div>
            <div class="segment-footer">
              <div class="segment-actions">
                <button :class="['seg-rate-btn', { active: seg.rating === 1 }]" @click="rateSegment(seg, 1)">👍</button>
                <button :class="['seg-rate-btn', { active: seg.rating === -1 }]" @click="rateSegment(seg, -1)">👎</button>
                <button class="seg-comment-btn" @click="commentingSegment = commentingSegment === seg.id ? null : seg.id">
                  💬 {{ seg.comment ? 'Edit' : 'Comment' }}
                </button>
              </div>
            </div>
            <div v-if="seg.comment" class="existing-comment">
              <span class="comment-icon">💬</span>
              <span class="comment-text">{{ seg.comment }}</span>
            </div>
            <div v-if="commentingSegment === seg.id" class="comment-input-area">
              <textarea v-model="newComment" class="comment-textarea" placeholder="Add your feedback..." rows="2"></textarea>
              <div class="comment-input-actions">
                <button class="btn btn-ghost btn-sm" @click="commentingSegment = null; newComment = ''">Cancel</button>
                <button class="btn btn-primary btn-sm" @click="addComment(seg)">Save</button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.exec-annotation { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.stat-chip { padding: 14px 18px; text-align: center; }
.stat-num { font-size: 1.4rem; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.stat-label { font-size: 0.72rem; color: var(--text-muted); }

.layout { display: grid; grid-template-columns: 220px 1fr; gap: 20px; align-items: start; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.sidebar { display: flex; flex-direction: column; gap: 10px; }
.exec-item { padding: 12px 14px; cursor: pointer; transition: all 0.1s; }
.exec-item.active { border-color: var(--accent-cyan); box-shadow: 0 0 0 1px var(--accent-cyan); }
.exec-item:hover:not(.active) { border-color: var(--border-default); background: var(--bg-tertiary); }
.exec-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.exec-bot { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
.thumb { font-size: 0.9rem; }
.exec-date { font-size: 0.72rem; color: var(--text-muted); margin-bottom: 2px; }
.exec-score { font-size: 0.72rem; color: var(--accent-cyan); }

.annotation-main { display: flex; flex-direction: column; gap: 12px; }
.exec-header-content { display: flex; align-items: flex-start; justify-content: space-between; padding: 16px 20px; }
.exec-title { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.exec-time { font-size: 0.75rem; color: var(--text-muted); }
.overall-rating { display: flex; align-items: center; gap: 8px; }
.rating-label { font-size: 0.78rem; color: var(--text-tertiary); }
.rate-btn { background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 6px; padding: 6px 10px; cursor: pointer; font-size: 1rem; transition: all 0.15s; }
.rate-btn.active { border-color: var(--accent-cyan); background: rgba(6,182,212,0.1); }
.rate-btn:disabled { opacity: 0.4; }

.segments-list { display: flex; flex-direction: column; gap: 10px; }
.segment-card { padding: 0; }
.segment-text { padding: 16px 18px; font-size: 0.82rem; color: var(--text-secondary); line-height: 1.6; white-space: pre-wrap; }
.segment-footer { display: flex; align-items: center; padding: 10px 18px; border-top: 1px solid var(--border-subtle); background: var(--bg-tertiary); }
.segment-actions { display: flex; gap: 8px; align-items: center; }
.seg-rate-btn { background: none; border: 1px solid var(--border-default); border-radius: 5px; padding: 4px 8px; cursor: pointer; font-size: 0.88rem; transition: all 0.15s; }
.seg-rate-btn.active { border-color: var(--accent-cyan); background: rgba(6,182,212,0.1); }
.seg-comment-btn { background: none; border: 1px solid var(--border-default); border-radius: 5px; padding: 4px 10px; cursor: pointer; font-size: 0.75rem; color: var(--text-tertiary); transition: all 0.15s; }
.seg-comment-btn:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.existing-comment { display: flex; align-items: flex-start; gap: 8px; padding: 10px 18px; background: rgba(6,182,212,0.04); border-top: 1px solid rgba(6,182,212,0.1); }
.comment-icon { font-size: 0.82rem; flex-shrink: 0; }
.comment-text { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.4; }
.comment-input-area { padding: 12px 18px; border-top: 1px solid var(--border-subtle); display: flex; flex-direction: column; gap: 8px; }
.comment-textarea { padding: 8px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-primary); font-size: 0.8rem; font-family: inherit; resize: vertical; }
.comment-textarea:focus { outline: none; border-color: var(--accent-cyan); }
.comment-input-actions { display: flex; justify-content: flex-end; gap: 8px; }

.btn { display: flex; align-items: center; padding: 6px 12px; border-radius: 6px; font-size: 0.78rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover { opacity: 0.85; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-sm { padding: 4px 10px; font-size: 0.72rem; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .stats-row { grid-template-columns: repeat(2, 1fr); } }
</style>
