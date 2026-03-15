<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import { triggerApi, analyticsApi, ApiError } from '../services/api';
import type { Trigger } from '../services/api';

const router = useRouter();
const showToast = useToast();

const isLoading = ref(true);
const error = ref('');

interface BotRecommendation {
  id: string;
  templateId: string;
  name: string;
  description: string;
  reason: string;
  relevanceScore: number;
  category: 'security' | 'quality' | 'productivity' | 'monitoring';
  estimatedTimeSaved: string;
  installed: boolean;
}

const recommendations = ref<BotRecommendation[]>([]);

const isInstalling = ref<string | null>(null);
const filterCategory = ref<string>('');

const filtered = computed(() => {
  if (!filterCategory.value) return recommendations.value;
  return recommendations.value.filter(r => r.category === filterCategory.value);
});

const categories = ['security', 'quality', 'productivity', 'monitoring'];

function categorizeSource(source: string): BotRecommendation['category'] {
  if (source === 'github') return 'quality';
  if (source === 'schedule') return 'monitoring';
  if (source === 'webhook') return 'security';
  return 'productivity';
}

async function loadRecommendations() {
  isLoading.value = true;
  error.value = '';
  try {
    const [triggersResp, effectResp] = await Promise.all([
      triggerApi.list(),
      analyticsApi.fetchEffectiveness().catch(() => null),
    ]);

    const triggers = triggersResp.triggers ?? [];
    const acceptanceRate = effectResp?.acceptance_rate ?? 0;

    recommendations.value = triggers.map((t: Trigger, idx: number) => {
      const category = categorizeSource(t.trigger_source);
      const score = Math.max(50, 100 - idx * 8 - (t.enabled ? 0 : 15));
      const timeSaved = t.timeout_seconds
        ? `${Math.round((t.timeout_seconds / 3600) * 10) / 10} hrs/week`
        : '1 hr/week';

      return {
        id: t.id,
        templateId: t.id,
        name: t.name,
        description: t.prompt_template
          ? t.prompt_template.substring(0, 120) + (t.prompt_template.length > 120 ? '...' : '')
          : `${t.trigger_source} trigger using ${t.backend_type}`,
        reason: acceptanceRate > 0
          ? `Current effectiveness rate: ${(acceptanceRate * 100).toFixed(0)}%. This trigger (${t.trigger_source}) can improve automation coverage.`
          : `This ${t.trigger_source} trigger uses ${t.backend_type} and ${t.model ?? 'default model'}.`,
        relevanceScore: Math.min(99, score),
        category,
        estimatedTimeSaved: timeSaved,
        installed: !!t.enabled,
      };
    });

    // Sort by relevance score descending
    recommendations.value.sort((a, b) => b.relevanceScore - a.relevanceScore);
  } catch (e) {
    if (e instanceof ApiError) {
      error.value = e.message;
    } else {
      error.value = 'Failed to load recommendations';
    }
    showToast(error.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

async function installBot(rec: BotRecommendation) {
  isInstalling.value = rec.id;
  try {
    await triggerApi.update(rec.id, { enabled: 1 });
    rec.installed = true;
    showToast(`${rec.name} enabled successfully`, 'success');
  } catch {
    showToast(`Failed to enable ${rec.name}`, 'error');
  } finally {
    isInstalling.value = null;
  }
}

function categoryColor(cat: BotRecommendation['category']) {
  return { security: '#ef4444', quality: 'var(--accent-cyan)', productivity: '#34d399', monitoring: '#fbbf24' }[cat];
}

function scoreColor(score: number) {
  if (score >= 90) return '#34d399';
  if (score >= 75) return '#fbbf24';
  return 'var(--text-muted)';
}

onMounted(loadRecommendations);
</script>

<template>
  <div class="rec-engine">

    <PageHeader
      title="Bot Recommendation Engine"
      subtitle="Personalized bot suggestions based on your team's repos, PRs, and incident history."
    />

    <LoadingState v-if="isLoading" message="Loading recommendations..." />

    <div v-else-if="error" class="card error-state">
      <p class="error-text">{{ error }}</p>
      <button class="btn btn-primary" @click="loadRecommendations">Retry</button>
    </div>

    <template v-else>
      <div class="filters-row">
        <button
          :class="['filter-pill', { active: filterCategory === '' }]"
          @click="filterCategory = ''"
        >All</button>
        <button
          v-for="cat in categories"
          :key="cat"
          :class="['filter-pill', { active: filterCategory === cat }]"
          @click="filterCategory = cat"
        >{{ cat }}</button>
      </div>

      <div class="recs-list">
        <div v-for="rec in filtered" :key="rec.id" class="rec-card card">
          <div class="rec-left">
            <div class="relevance-circle" :style="{ borderColor: scoreColor(rec.relevanceScore) }">
              <span class="relevance-val" :style="{ color: scoreColor(rec.relevanceScore) }">{{ rec.relevanceScore }}</span>
              <span class="relevance-label">match</span>
            </div>
          </div>
          <div class="rec-content">
            <div class="rec-top">
              <div>
                <div class="rec-name">{{ rec.name }}</div>
                <span class="rec-category" :style="{ background: `${categoryColor(rec.category)}18`, color: categoryColor(rec.category) }">{{ rec.category }}</span>
              </div>
              <div class="rec-actions">
                <span class="time-saved">{{ rec.estimatedTimeSaved }} saved</span>
                <button
                  v-if="!rec.installed"
                  class="btn btn-primary"
                  :disabled="isInstalling === rec.id"
                  @click="installBot(rec)"
                >{{ isInstalling === rec.id ? 'Installing...' : 'Install' }}</button>
                <span v-else class="installed-badge">Installed</span>
              </div>
            </div>
            <div class="rec-description">{{ rec.description }}</div>
            <div class="rec-reason">
              <span class="reason-icon">*</span>
              {{ rec.reason }}
            </div>
          </div>
        </div>

        <div v-if="filtered.length === 0" class="empty-state card">
          <p>No recommendations for this category yet.</p>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.rec-engine { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.error-state { padding: 32px 24px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.error-text { font-size: 0.875rem; color: #ef4444; margin: 0; }

.filters-row { display: flex; gap: 8px; flex-wrap: wrap; }
.filter-pill { padding: 6px 16px; border-radius: 20px; font-size: 0.8rem; font-weight: 500; border: 1px solid var(--border-default); background: var(--bg-secondary); color: var(--text-secondary); cursor: pointer; text-transform: capitalize; transition: all 0.15s; }
.filter-pill.active { background: var(--accent-cyan); color: #000; border-color: var(--accent-cyan); }
.filter-pill:hover:not(.active) { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.recs-list { display: flex; flex-direction: column; gap: 12px; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.rec-card { display: flex; gap: 0; }
.rec-left { padding: 20px; border-right: 1px solid var(--border-default); display: flex; align-items: flex-start; }
.relevance-circle { width: 60px; height: 60px; border-radius: 50%; border: 2px solid; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-shrink: 0; }
.relevance-val { font-size: 1rem; font-weight: 700; line-height: 1; }
.relevance-label { font-size: 0.6rem; color: var(--text-muted); }

.rec-content { flex: 1; padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }
.rec-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.rec-name { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.rec-category { font-size: 0.68rem; font-weight: 700; padding: 2px 8px; border-radius: 4px; text-transform: capitalize; }
.rec-actions { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.time-saved { font-size: 0.75rem; color: var(--text-tertiary); }
.installed-badge { font-size: 0.78rem; color: #34d399; font-weight: 600; }

.rec-description { font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5; }

.rec-reason { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; background: rgba(251,191,36,0.06); border-radius: 7px; border: 1px solid rgba(251,191,36,0.12); }
.reason-icon { font-size: 0.9rem; flex-shrink: 0; margin-top: 1px; }
.rec-reason { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.4; }

.empty-state { padding: 48px 24px; text-align: center; }
.empty-state p { font-size: 0.875rem; color: var(--text-tertiary); margin: 0; }

.btn { padding: 7px 14px; border-radius: 7px; font-size: 0.8rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 700px) { .rec-card { flex-direction: column; } .rec-left { border-right: none; border-bottom: 1px solid var(--border-default); } }
</style>
