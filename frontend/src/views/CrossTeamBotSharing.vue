<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface SharedBot {
  id: string;
  name: string;
  description: string;
  team: string;
  stars: number;
  forks: number;
  tags: string[];
  version: string;
  updatedAt: string;
  isSubscribed: boolean;
  isForked: boolean;
}

interface MySharedBot {
  id: string;
  name: string;
  sharedWith: string[];
  subscribers: number;
}

const tab = ref<'browse' | 'mine'>('browse');
const searchQuery = ref('');
const processingId = ref<string | null>(null);

const sharedBots = ref<SharedBot[]>([
  { id: 'sb-1', name: 'Dependency Vulnerability Scanner', description: 'Scans package.json and Cargo.toml for known CVEs. Creates Jira tickets for critical findings.', team: 'Security Team', stars: 24, forks: 8, tags: ['security', 'dependencies', 'CVE'], version: '1.3.2', updatedAt: '2 days ago', isSubscribed: false, isForked: false },
  { id: 'sb-2', name: 'API Contract Linter', description: 'Validates OpenAPI specs against team standards. Blocks PRs with breaking changes.', team: 'Platform Team', stars: 18, forks: 5, tags: ['api', 'openapi', 'linting'], version: '2.0.0', updatedAt: '1 week ago', isSubscribed: true, isForked: false },
  { id: 'sb-3', name: 'Test Coverage Guardian', description: 'Ensures test coverage does not drop below threshold. Comments coverage delta on PRs.', team: 'Quality Team', stars: 31, forks: 12, tags: ['testing', 'coverage', 'ci'], version: '3.1.0', updatedAt: '3 days ago', isSubscribed: false, isForked: true },
  { id: 'sb-4', name: 'Database Migration Reviewer', description: 'Reviews SQL migrations for destructive operations and missing rollbacks.', team: 'Backend Team', stars: 9, forks: 2, tags: ['database', 'migrations', 'sql'], version: '1.0.1', updatedAt: '2 weeks ago', isSubscribed: false, isForked: false },
]);

const myBots = ref<MySharedBot[]>([
  { id: 'my-sb-1', name: 'Security Audit Bot', sharedWith: ['Platform Team', 'Quality Team'], subscribers: 7 },
  { id: 'my-sb-2', name: 'PR Review Bot', sharedWith: [], subscribers: 0 },
]);

const filtered = computed(() => {
  const q = searchQuery.value.toLowerCase();
  if (!q) return sharedBots.value;
  return sharedBots.value.filter(b =>
    b.name.toLowerCase().includes(q) ||
    b.description.toLowerCase().includes(q) ||
    b.tags.some(t => t.includes(q)) ||
    b.team.toLowerCase().includes(q)
  );
});

async function handleFork(bot: SharedBot) {
  processingId.value = bot.id;
  try {
    await new Promise(resolve => setTimeout(resolve, 1000));
    bot.isForked = true;
    bot.forks++;
    showToast(`"${bot.name}" forked to your team`, 'success');
  } catch {
    showToast('Failed to fork bot', 'error');
  } finally {
    processingId.value = null;
  }
}

async function handleSubscribe(bot: SharedBot) {
  bot.isSubscribed = !bot.isSubscribed;
  showToast(bot.isSubscribed ? `Subscribed to updates from "${bot.name}"` : `Unsubscribed from "${bot.name}"`, 'success');
}

async function handleShare(bot: MySharedBot) {
  showToast(`"${bot.name}" is now publicly shared`, 'success');
}
</script>

<template>
  <div class="bot-sharing">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: 'Bot Sharing' },
    ]" />

    <PageHeader
      title="Cross-Team Bot Sharing"
      subtitle="Browse, fork, and share bots across teams in your organization."
    />

    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: tab === 'browse' }" @click="tab = 'browse'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        Browse Shared Bots
      </button>
      <button class="tab-btn" :class="{ active: tab === 'mine' }" @click="tab = 'mine'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <circle cx="12" cy="7" r="4"/><path d="M5 21v-2a7 7 0 0 1 14 0v2"/>
        </svg>
        My Shared Bots
      </button>
    </div>

    <template v-if="tab === 'browse'">
      <div class="search-row">
        <input
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="Search by name, description, tags, or team..."
        />
        <span class="search-count">{{ filtered.length }} bot{{ filtered.length !== 1 ? 's' : '' }}</span>
      </div>

      <div class="bots-grid">
        <div v-for="bot in filtered" :key="bot.id" class="card bot-card">
          <div class="bot-card-header">
            <div class="bot-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="20" height="20">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <path d="M9 9h6M9 12h6M9 15h4"/>
              </svg>
            </div>
            <div class="bot-title-area">
              <h3 class="bot-card-name">{{ bot.name }}</h3>
              <span class="bot-team">{{ bot.team }}</span>
            </div>
            <span class="bot-version">v{{ bot.version }}</span>
          </div>

          <p class="bot-desc">{{ bot.description }}</p>

          <div class="bot-tags">
            <span v-for="tag in bot.tags" :key="tag" class="tag">{{ tag }}</span>
          </div>

          <div class="bot-stats">
            <span class="stat">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              {{ bot.stars }}
            </span>
            <span class="stat">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg>
              {{ bot.forks }}
            </span>
            <span class="stat-date">Updated {{ bot.updatedAt }}</span>
          </div>

          <div class="bot-card-actions">
            <button
              class="btn btn-sm"
              :class="bot.isSubscribed ? 'btn-subscribed' : 'btn-secondary'"
              @click="handleSubscribe(bot)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0"/>
              </svg>
              {{ bot.isSubscribed ? 'Subscribed' : 'Subscribe' }}
            </button>
            <button
              class="btn btn-sm"
              :class="bot.isForked ? 'btn-forked' : 'btn-primary'"
              :disabled="bot.isForked || processingId === bot.id"
              @click="handleFork(bot)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>
              </svg>
              {{ bot.isForked ? 'Forked' : processingId === bot.id ? '...' : 'Fork' }}
            </button>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
            </svg>
            My Bots Available for Sharing
          </h3>
        </div>
        <div class="my-bots-list">
          <div v-for="bot in myBots" :key="bot.id" class="my-bot-row">
            <div class="my-bot-info">
              <span class="my-bot-name">{{ bot.name }}</span>
              <span class="my-bot-subs">{{ bot.subscribers }} subscribers</span>
            </div>
            <div class="my-bot-shared">
              <template v-if="bot.sharedWith.length > 0">
                <span v-for="t in bot.sharedWith" :key="t" class="shared-tag">{{ t }}</span>
              </template>
              <span v-else class="not-shared">Not shared</span>
            </div>
            <div class="my-bot-actions">
              <button class="btn btn-sm btn-secondary" @click="handleShare(bot)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
                  <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
                </svg>
                Share
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.bot-sharing {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.tab-bar {
  display: flex;
  gap: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 4px;
  width: fit-content;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn.active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.search-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.search-input {
  flex: 1;
  padding: 9px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.search-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.search-count {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.bots-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.bot-card {
  padding: 0;
  display: flex;
  flex-direction: column;
}

.bot-card-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 18px 18px 14px;
}

.bot-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--accent-cyan);
}

.bot-title-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bot-card-name {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.bot-team {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.bot-version {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  font-family: monospace;
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
}

.bot-desc {
  font-size: 0.85rem;
  color: var(--text-secondary);
  padding: 0 18px;
  margin: 0 0 12px;
  line-height: 1.5;
}

.bot-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 18px 12px;
}

.tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-tertiary);
}

.bot-stats {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 18px 12px;
}

.stat {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

.stat-date {
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-left: auto;
}

.bot-card-actions {
  display: flex;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid var(--border-subtle);
  margin-top: auto;
}

.my-bots-list {
  display: flex;
  flex-direction: column;
}

.my-bot-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-subtle);
}

.my-bot-row:last-child { border-bottom: none; }

.my-bot-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.my-bot-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.my-bot-subs {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.my-bot-shared {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.shared-tag {
  font-size: 0.72rem;
  padding: 2px 8px;
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.2);
  border-radius: 4px;
  color: var(--accent-cyan);
}

.not-shared {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.btn {
  display: flex;
  align-items: center;
  gap: 5px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 6px 12px; font-size: 0.8rem; }

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.btn-subscribed {
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.3);
  color: var(--accent-cyan);
}

.btn-forked {
  background: rgba(52, 211, 153, 0.1);
  border: 1px solid rgba(52, 211, 153, 0.3);
  color: #34d399;
  cursor: default;
}

@media (max-width: 768px) {
  .bots-grid { grid-template-columns: 1fr; }
}
</style>
