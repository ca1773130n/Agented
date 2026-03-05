<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

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
}

const annotations = ref<PRAnnotation[]>([
  { id: 'ann-001', pr: '#142 Add OAuth flow', repo: 'org/api', postedAt: '2026-03-06T14:30:00Z', comments: 5, status: 'posted', severity: 'warning' },
  { id: 'ann-002', pr: '#138 Refactor DB layer', repo: 'org/backend', postedAt: '2026-03-05T10:00:00Z', comments: 2, status: 'posted', severity: 'info' },
  { id: 'ann-003', pr: '#145 Update dependencies', repo: 'org/frontend', postedAt: '2026-03-06T08:15:00Z', comments: 8, status: 'pending', severity: 'error' },
  { id: 'ann-004', pr: '#131 Fix SSE reconnect', repo: 'org/api', postedAt: '2026-03-04T17:00:00Z', comments: 3, status: 'failed', severity: 'info' },
]);

const selected = ref<PRAnnotation | null>(null);
const isPosting = ref(false);

interface InlineComment {
  file: string;
  line: number;
  body: string;
  severity: 'info' | 'warning' | 'error';
}

const mockComments: InlineComment[] = [
  { file: 'src/auth/oauth.ts', line: 42, body: '**Potential CSRF vulnerability**: OAuth callback does not validate the `state` parameter. Add `state` verification before exchanging the authorization code.', severity: 'error' },
  { file: 'src/auth/oauth.ts', line: 78, body: 'Access tokens stored in `localStorage` are accessible via XSS. Consider using `httpOnly` cookies instead.', severity: 'warning' },
  { file: 'src/middleware/session.ts', line: 15, body: 'Session secret is hardcoded. Load from environment variable instead.', severity: 'error' },
];

async function handlePost(ann: PRAnnotation) {
  isPosting.value = true;
  try {
    await new Promise(r => setTimeout(r, 1200));
    ann.status = 'posted';
    showToast(`Posted ${mockComments.length} inline comments to ${ann.pr}`, 'success');
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

function severityClass(s: InlineComment['severity']) {
  return { error: 'sev-error', warning: 'sev-warn', info: 'sev-info' }[s];
}
</script>

<template>
  <div class="pr-annotation">
    <AppBreadcrumb :items="[
      { label: 'Integrations', action: () => router.push({ name: 'triggers' }) },
      { label: 'GitHub PR Annotations' },
    ]" />

    <PageHeader
      title="GitHub PR Annotation Integration"
      subtitle="Post bot review findings as inline comments directly on GitHub pull request diffs."
    />

    <div class="layout">
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
            <span class="comment-count">{{ ann.comments }} comments</span>
          </div>
        </div>
      </div>

      <div class="detail-panel">
        <div v-if="!selected" class="card empty-state">
          <p>Select a PR to view its inline annotations</p>
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
            <div v-for="(c, i) in mockComments" :key="i" :class="['comment-card', severityClass(c.severity)]">
              <div class="comment-location">
                <span class="comment-file">{{ c.file }}</span>
                <span class="comment-line">Line {{ c.line }}</span>
              </div>
              <div class="comment-body">{{ c.body }}</div>
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
