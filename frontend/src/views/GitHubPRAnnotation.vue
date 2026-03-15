<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { prReviewApi, ApiError } from '../services/api';
import type { PrReview } from '../services/api';

const router = useRouter();
const showToast = useToast();

interface PRAnnotation {
  id: string;
  pr: string;
  repo: string;
  postedAt: string;
  comments: number;
  status: 'posted' | 'pending' | 'failed';
  severity: 'info' | 'warning' | 'error';
  reviewComment: string;
}

const loading = ref(true);
const error = ref('');
const annotations = ref<PRAnnotation[]>([]);
const selected = ref<PRAnnotation | null>(null);
const isPosting = ref(false);

function reviewStatusToAnnotationStatus(review: PrReview): 'posted' | 'pending' | 'failed' {
  if (review.review_status === 'approved' || review.review_status === 'fixed') return 'posted';
  if (review.review_status === 'changes_requested') return 'pending';
  if (review.review_status === 'pending') return 'pending';
  return 'posted';
}

function reviewToSeverity(review: PrReview): 'info' | 'warning' | 'error' {
  if (review.review_status === 'changes_requested') return 'error';
  if (review.review_status === 'pending') return 'warning';
  return 'info';
}

function prReviewToAnnotation(review: PrReview): PRAnnotation {
  return {
    id: String(review.id),
    pr: `#${review.pr_number} ${review.pr_title}`,
    repo: review.github_repo_url || review.project_name,
    postedAt: review.created_at || review.updated_at || new Date().toISOString(),
    comments: review.fixes_applied || 0,
    status: reviewStatusToAnnotationStatus(review),
    severity: reviewToSeverity(review),
    reviewComment: review.review_comment || '',
  };
}

async function fetchReviews() {
  loading.value = true;
  error.value = '';
  try {
    const result = await prReviewApi.list({ limit: 20 });
    annotations.value = (result?.reviews || []).map(prReviewToAnnotation);
  } catch (err) {
    if (err instanceof ApiError) {
      error.value = `Failed to load PR reviews: ${err.message}`;
    } else {
      error.value = 'Failed to load PR reviews';
    }
  } finally {
    loading.value = false;
  }
}

onMounted(fetchReviews);

async function handlePost(ann: PRAnnotation) {
  isPosting.value = true;
  try {
    await prReviewApi.update(Number(ann.id), { review_status: 'approved' });
    ann.status = 'posted';
    showToast(`Annotations posted to ${ann.pr}`, 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : 'Failed to post annotations', 'error');
  } finally {
    isPosting.value = false;
  }
}

function formatDate(ts: string) {
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function statusClass(s: PRAnnotation['status']) {
  return { posted: 'status-ok', pending: 'status-warn', failed: 'status-err' }[s];
}
</script>

<template>
  <div class="pr-annotation">

    <PageHeader
      title="GitHub PR Annotation Integration"
      subtitle="Post bot review findings as inline comments directly on GitHub pull request diffs."
    />

    <!-- Loading state -->
    <div v-if="loading" class="card" style="padding: 48px; text-align: center;">
      <div style="color: var(--text-tertiary); font-size: 0.875rem;">Loading PR reviews...</div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="card" style="padding: 48px; text-align: center;">
      <div style="color: #ef4444; font-size: 0.875rem; margin-bottom: 12px;">{{ error }}</div>
      <button class="btn btn-primary" @click="fetchReviews">Retry</button>
    </div>

    <!-- Empty state -->
    <div v-else-if="annotations.length === 0" class="card" style="padding: 48px; text-align: center;">
      <div style="color: var(--text-tertiary); font-size: 0.875rem;">No PR reviews available for annotation.</div>
    </div>

    <div v-else class="layout">
      <div class="pr-list card">
        <div class="list-header">Recent PR Reviews</div>
        <div
          v-for="ann in annotations"
          :key="ann.id"
          class="pr-item"
          :class="{ active: selected?.id === ann.id }"
          @click="selected = ann"
        >
          <div class="pr-top">
            <span class="pr-title">{{ ann.pr }}</span>
            <span :class="['pr-status', statusClass(ann.status)]">{{ ann.status }}</span>
          </div>
          <div class="pr-meta">
            <span class="pr-repo">{{ ann.repo }}</span>
            <span class="pr-date">{{ formatDate(ann.postedAt) }}</span>
          </div>
          <div class="pr-stats">
            <span :class="['sev-badge', `sev-${ann.severity}`]">{{ ann.severity }}</span>
            <span class="comment-count">{{ ann.comments }} fixes</span>
          </div>
        </div>
      </div>

      <div class="detail-panel">
        <div v-if="!selected" class="card empty-state">
          <p>Select a PR to view its annotation details</p>
        </div>

        <div v-else class="card pr-detail">
          <div class="detail-header">
            <div>
              <div class="detail-pr-title">{{ selected.pr }}</div>
              <div class="detail-repo">{{ selected.repo }} · {{ formatDate(selected.postedAt) }}</div>
            </div>
            <button
              class="btn btn-primary"
              :disabled="isPosting || selected.status === 'posted'"
              @click="handlePost(selected)"
            >
              {{ isPosting ? 'Posting...' : selected.status === 'posted' ? 'Posted' : 'Post to GitHub' }}
            </button>
          </div>

          <div class="comments-list">
            <div v-if="selected.reviewComment" class="comment-card sev-info">
              <div class="comment-location">
                <span class="comment-file">Review Comment</span>
              </div>
              <div class="comment-body">{{ selected.reviewComment }}</div>
            </div>
            <div v-if="!selected.reviewComment" class="comment-card sev-info">
              <div class="comment-location">
                <span class="comment-file">Status</span>
              </div>
              <div class="comment-body">
                This PR review has {{ selected.comments }} fixes applied.
                Status: {{ selected.status }}.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pr-annotation { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 300px 1fr; gap: 20px; align-items: start; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.list-header { padding: 14px 18px; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); border-bottom: 1px solid var(--border-default); }

.pr-item { padding: 12px 18px; cursor: pointer; border-bottom: 1px solid var(--border-subtle); transition: background 0.1s; }
.pr-item:hover { background: var(--bg-tertiary); }
.pr-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.pr-item:last-child { border-bottom: none; }

.pr-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.pr-title { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
.pr-status { font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 3px; }
.status-ok { background: rgba(52,211,153,0.15); color: #34d399; }
.status-warn { background: rgba(251,191,36,0.15); color: #fbbf24; }
.status-err { background: rgba(239,68,68,0.15); color: #ef4444; }

.pr-meta { display: flex; justify-content: space-between; margin-bottom: 6px; }
.pr-repo { font-size: 0.72rem; color: var(--text-tertiary); }
.pr-date { font-size: 0.7rem; color: var(--text-muted); }
.pr-stats { display: flex; align-items: center; gap: 8px; }
.sev-badge { font-size: 0.68rem; font-weight: 700; padding: 2px 6px; border-radius: 3px; text-transform: capitalize; }
.sev-error { background: rgba(239,68,68,0.15); color: #ef4444; }
.sev-warn, .sev-warning { background: rgba(251,191,36,0.15); color: #fbbf24; }
.sev-info { background: rgba(6,182,212,0.15); color: var(--accent-cyan); }
.comment-count { font-size: 0.72rem; color: var(--text-muted); }

.empty-state { padding: 64px 24px; text-align: center; }
.empty-state p { font-size: 0.875rem; color: var(--text-tertiary); margin: 0; }

.detail-header {
  display: flex; align-items: flex-start; justify-content: space-between; padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}
.detail-pr-title { font-size: 1rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.detail-repo { font-size: 0.78rem; color: var(--text-tertiary); }

.btn { padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.comments-list { display: flex; flex-direction: column; gap: 1px; }

.comment-card { padding: 16px 24px; border-bottom: 1px solid var(--border-subtle); border-left: 3px solid transparent; }
.comment-card:last-child { border-bottom: none; }
.comment-card.sev-error { border-left-color: #ef4444; background: rgba(239,68,68,0.03); }
.comment-card.sev-warn { border-left-color: #fbbf24; background: rgba(251,191,36,0.03); }
.comment-card.sev-info { border-left-color: var(--accent-cyan); background: rgba(6,182,212,0.03); }

.comment-location { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.comment-file { font-family: monospace; font-size: 0.78rem; color: var(--text-primary); }
.comment-line { font-size: 0.72rem; color: var(--text-muted); background: var(--bg-tertiary); padding: 2px 6px; border-radius: 3px; }
.comment-body { font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
