<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

type Category = 'all' | 'security' | 'code-quality' | 'devops' | 'productivity' | 'testing' | 'documentation';

interface MarketplaceSkill {
  id: string;
  name: string;
  author: string;
  authorOrg: string;
  description: string;
  category: string;
  tags: string[];
  rating: number;
  ratingCount: number;
  usageCount: number;
  version: string;
  updatedAt: string;
  installed: boolean;
  official: boolean;
}

const skills = ref<MarketplaceSkill[]>([
  {
    id: 'sk-m-001',
    name: 'OWASP Security Scanner',
    author: 'security-team',
    authorOrg: 'Agented Official',
    description: 'Comprehensive OWASP Top 10 vulnerability scanner with structured JSON output. Covers injection, XSS, CSRF, SSRF, and more.',
    category: 'security',
    tags: ['OWASP', 'vulnerability', 'JSON output'],
    rating: 4.9,
    ratingCount: 312,
    usageCount: 8400,
    version: '2.1.0',
    updatedAt: '2026-03-01T00:00:00Z',
    installed: true,
    official: true,
  },
  {
    id: 'sk-m-002',
    name: 'PR Review Pro',
    author: 'devtools',
    authorOrg: 'Agented Official',
    description: 'Deep pull request reviewer that checks logic, style, performance, and security. Posts inline GitHub comments.',
    category: 'code-quality',
    tags: ['PR review', 'inline comments', 'GitHub'],
    rating: 4.8,
    ratingCount: 229,
    usageCount: 6200,
    version: '3.0.1',
    updatedAt: '2026-02-25T00:00:00Z',
    installed: false,
    official: true,
  },
  {
    id: 'sk-m-003',
    name: 'Dependency Auditor',
    author: 'supply-chain',
    authorOrg: 'Agented Official',
    description: 'Analyzes package.json, requirements.txt, go.mod and Cargo.toml for security CVEs, license conflicts, and breaking changes.',
    category: 'security',
    tags: ['dependencies', 'CVE', 'license'],
    rating: 4.7,
    ratingCount: 180,
    usageCount: 4900,
    version: '1.4.2',
    updatedAt: '2026-02-20T00:00:00Z',
    installed: false,
    official: true,
  },
  {
    id: 'sk-m-004',
    name: 'Changelog Writer',
    author: 'docs-bot',
    authorOrg: 'Community',
    description: 'Reads commit messages and PR titles to write clean, user-facing CHANGELOG.md entries in Keep a Changelog format.',
    category: 'documentation',
    tags: ['changelog', 'commits', 'markdown'],
    rating: 4.6,
    ratingCount: 95,
    usageCount: 3100,
    version: '1.2.0',
    updatedAt: '2026-02-18T00:00:00Z',
    installed: true,
    official: false,
  },
  {
    id: 'sk-m-005',
    name: 'Test Failure Analyst',
    author: 'qa-team',
    authorOrg: 'Community',
    description: 'Parses CI test output, identifies failing tests, traces root causes through stack traces, and suggests fixes.',
    category: 'testing',
    tags: ['CI', 'test failures', 'debugging'],
    rating: 4.5,
    ratingCount: 143,
    usageCount: 2800,
    version: '2.0.0',
    updatedAt: '2026-02-15T00:00:00Z',
    installed: false,
    official: false,
  },
  {
    id: 'sk-m-006',
    name: 'Infrastructure Drift Detector',
    author: 'infra-dev',
    authorOrg: 'Community',
    description: 'Compares Terraform plan output against expected state and highlights unintended infrastructure changes.',
    category: 'devops',
    tags: ['Terraform', 'IaC', 'drift'],
    rating: 4.4,
    ratingCount: 67,
    usageCount: 1500,
    version: '1.0.3',
    updatedAt: '2026-02-10T00:00:00Z',
    installed: false,
    official: false,
  },
  {
    id: 'sk-m-007',
    name: 'API Contract Validator',
    author: 'api-guild',
    authorOrg: 'Community',
    description: 'Validates OpenAPI/Swagger specs for breaking changes, missing documentation, and schema inconsistencies.',
    category: 'code-quality',
    tags: ['OpenAPI', 'REST', 'breaking changes'],
    rating: 4.3,
    ratingCount: 54,
    usageCount: 1200,
    version: '1.1.0',
    updatedAt: '2026-02-05T00:00:00Z',
    installed: false,
    official: false,
  },
  {
    id: 'sk-m-008',
    name: 'Standup Summarizer',
    author: 'productivity-bots',
    authorOrg: 'Community',
    description: 'Generates concise daily standup summaries from recent commits, PR activity, and issue updates.',
    category: 'productivity',
    tags: ['standup', 'summaries', 'async'],
    rating: 4.2,
    ratingCount: 88,
    usageCount: 2200,
    version: '1.3.1',
    updatedAt: '2026-01-28T00:00:00Z',
    installed: false,
    official: false,
  },
]);

const searchQuery = ref('');
const activeCategory = ref<Category>('all');
const sortBy = ref<'rating' | 'usage' | 'updated'>('rating');
const isInstalling = ref<string | null>(null);

const categories: { key: Category; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'security', label: 'Security' },
  { key: 'code-quality', label: 'Code Quality' },
  { key: 'devops', label: 'DevOps' },
  { key: 'testing', label: 'Testing' },
  { key: 'documentation', label: 'Documentation' },
  { key: 'productivity', label: 'Productivity' },
];

const filtered = computed(() => {
  let list = skills.value;
  if (activeCategory.value !== 'all') {
    list = list.filter(s => s.category === activeCategory.value);
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase();
    list = list.filter(s =>
      s.name.toLowerCase().includes(q) ||
      s.description.toLowerCase().includes(q) ||
      s.tags.some(t => t.toLowerCase().includes(q))
    );
  }
  if (sortBy.value === 'rating') list = [...list].sort((a, b) => b.rating - a.rating);
  else if (sortBy.value === 'usage') list = [...list].sort((a, b) => b.usageCount - a.usageCount);
  else list = [...list].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  return list;
});

async function installSkill(skill: MarketplaceSkill) {
  isInstalling.value = skill.id;
  try {
    await new Promise(r => setTimeout(r, 900));
    skill.installed = true;
    skill.usageCount += 1;
    showToast(`"${skill.name}" installed successfully.`, 'success');
  } finally {
    isInstalling.value = null;
  }
}

async function uninstallSkill(skill: MarketplaceSkill) {
  skill.installed = false;
  showToast(`"${skill.name}" uninstalled.`, 'success');
}

function fmtCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function renderStars(rating: number): string {
  const full = Math.floor(rating);
  return '★'.repeat(full) + (rating % 1 >= 0.5 ? '½' : '') + '☆'.repeat(5 - Math.ceil(rating));
}
</script>

<template>
  <div class="skill-marketplace">
    <AppBreadcrumb :items="[
      { label: 'Skills', action: () => router.push({ name: 'skills' }) },
      { label: 'Marketplace' },
    ]" />

    <PageHeader
      title="Skill Marketplace"
      subtitle="Community and official skills — import into any agent with one click. Includes ratings, usage counts, and version history."
    />

    <!-- Search + sort bar -->
    <div class="search-bar card">
      <div class="search-input-wrap">
        <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input v-model="searchQuery" class="search-input" placeholder="Search skills by name, description, or tag…" />
      </div>
      <div class="sort-row">
        <span class="sort-label">Sort:</span>
        <select v-model="sortBy" class="select select-sm">
          <option value="rating">Top Rated</option>
          <option value="usage">Most Used</option>
          <option value="updated">Recently Updated</option>
        </select>
      </div>
    </div>

    <div class="marketplace-layout">
      <!-- Category sidebar -->
      <aside class="category-sidebar card">
        <div class="sidebar-title">Categories</div>
        <button
          v-for="cat in categories"
          :key="cat.key"
          class="cat-btn"
          :class="{ active: activeCategory === cat.key }"
          @click="activeCategory = cat.key"
        >
          {{ cat.label }}
          <span class="cat-count">{{ cat.key === 'all' ? skills.length : skills.filter(s => s.category === cat.key).length }}</span>
        </button>
      </aside>

      <!-- Skill grid -->
      <div class="skill-grid">
        <div v-if="filtered.length === 0" class="empty-state">
          <div class="empty-icon">🔍</div>
          <p>No skills match your search. Try a different keyword or category.</p>
        </div>

        <div v-for="skill in filtered" :key="skill.id" class="skill-card card">
          <div class="skill-header">
            <div class="skill-name-row">
              <span class="skill-name">{{ skill.name }}</span>
              <span v-if="skill.official" class="official-badge">Official</span>
            </div>
            <div class="skill-author">by {{ skill.author }} · {{ skill.authorOrg }}</div>
          </div>

          <div class="skill-desc">{{ skill.description }}</div>

          <div class="skill-tags">
            <span v-for="tag in skill.tags" :key="tag" class="skill-tag">{{ tag }}</span>
          </div>

          <div class="skill-meta">
            <span class="stars" :title="`${skill.rating} / 5`">{{ renderStars(skill.rating) }}</span>
            <span class="rating-val">{{ skill.rating.toFixed(1) }}</span>
            <span class="rating-count">({{ fmtCount(skill.ratingCount) }})</span>
            <span class="meta-sep">·</span>
            <span class="usage-count">{{ fmtCount(skill.usageCount) }} installs</span>
            <span class="meta-sep">·</span>
            <span class="version">v{{ skill.version }}</span>
          </div>

          <div class="skill-footer">
            <span class="updated">Updated {{ fmtDate(skill.updatedAt) }}</span>
            <div class="footer-actions">
              <button
                v-if="!skill.installed"
                class="btn btn-primary btn-sm"
                :disabled="isInstalling === skill.id"
                @click="installSkill(skill)"
              >
                {{ isInstalling === skill.id ? 'Installing…' : 'Install' }}
              </button>
              <button v-else class="btn btn-installed btn-sm" @click="uninstallSkill(skill)">
                ✓ Installed
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skill-marketplace { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 10px; }

/* Search */
.search-bar { padding: 12px 16px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.search-input-wrap { flex: 1; position: relative; display: flex; align-items: center; }
.search-icon { position: absolute; left: 10px; color: var(--text-tertiary); pointer-events: none; }
.search-input { width: 100%; padding: 8px 12px 8px 34px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; }
.search-input:focus { outline: none; border-color: var(--accent-cyan); }
.sort-row { display: flex; align-items: center; gap: 8px; }
.sort-label { font-size: 0.78rem; color: var(--text-tertiary); }
.select { padding: 7px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }
.select-sm { font-size: 0.78rem; padding: 5px 8px; }

/* Layout */
.marketplace-layout { display: grid; grid-template-columns: 180px 1fr; gap: 16px; align-items: start; }

/* Category sidebar */
.category-sidebar { padding: 12px; }
.sidebar-title { font-size: 0.72rem; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; padding: 4px 8px 8px; }
.cat-btn { width: 100%; display: flex; align-items: center; justify-content: space-between; padding: 7px 10px; border-radius: 7px; border: none; background: transparent; color: var(--text-secondary); font-size: 0.82rem; cursor: pointer; transition: all 0.1s; }
.cat-btn:hover { background: var(--bg-tertiary); color: var(--text-primary); }
.cat-btn.active { background: rgba(6,182,212,0.1); color: var(--accent-cyan); font-weight: 500; }
.cat-count { font-size: 0.7rem; background: var(--bg-tertiary); padding: 1px 6px; border-radius: 10px; color: var(--text-tertiary); }

/* Skill grid */
.skill-grid { display: flex; flex-direction: column; gap: 12px; }

.skill-card { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.skill-header { display: flex; flex-direction: column; gap: 2px; }
.skill-name-row { display: flex; align-items: center; gap: 8px; }
.skill-name { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); }
.official-badge { font-size: 0.65rem; font-weight: 700; background: rgba(99,102,241,0.15); color: #818cf8; border: 1px solid rgba(99,102,241,0.25); padding: 1px 6px; border-radius: 4px; }
.skill-author { font-size: 0.75rem; color: var(--text-tertiary); }
.skill-desc { font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5; }

.skill-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.skill-tag { font-size: 0.72rem; background: var(--bg-tertiary); border: 1px solid var(--border-default); padding: 2px 8px; border-radius: 5px; color: var(--text-tertiary); }

.skill-meta { display: flex; align-items: center; gap: 5px; font-size: 0.78rem; flex-wrap: wrap; }
.stars { color: #fbbf24; letter-spacing: -1px; }
.rating-val { font-weight: 600; color: var(--text-primary); }
.rating-count { color: var(--text-tertiary); }
.meta-sep { color: var(--border-default); }
.usage-count, .version { color: var(--text-tertiary); }

.skill-footer { display: flex; align-items: center; justify-content: space-between; padding-top: 8px; border-top: 1px solid var(--border-default); }
.updated { font-size: 0.75rem; color: var(--text-tertiary); }
.footer-actions { }

.btn { padding: 7px 14px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-installed { background: rgba(52,211,153,0.12); border: 1px solid rgba(52,211,153,0.25); color: #34d399; }
.btn-installed:hover { background: rgba(248,113,113,0.1); border-color: rgba(248,113,113,0.25); color: #f87171; }
.btn-sm { padding: 5px 12px; font-size: 0.78rem; }

.empty-state { text-align: center; padding: 48px 20px; color: var(--text-secondary); }
.empty-icon { font-size: 2.5rem; margin-bottom: 12px; }
</style>
