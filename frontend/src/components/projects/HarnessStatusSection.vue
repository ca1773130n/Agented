<script setup lang="ts">
import type { Project } from '../../services/api';

defineProps<{
  project: Project;
  totalTeamCount: number;
}>();
</script>

<template>
  <!-- GitHub Repository -->
  <div v-if="project.github_repo" class="card">
    <div class="card-header">
      <h3>GitHub Repository</h3>
    </div>
    <div class="github-content">
      <a :href="'https://' + (project.github_host || 'github.com') + '/' + project.github_repo" target="_blank" rel="noopener noreferrer" class="github-link">
        <svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
          <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
        </svg>
        <span>{{ project.github_repo }}</span>
        <svg class="external-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/>
        </svg>
      </a>
    </div>
  </div>

  <!-- Project Info -->
  <div class="card">
    <div class="card-header">
      <h3>Project Info</h3>
    </div>
    <div class="info-grid">
      <div class="info-item">
        <span class="info-label">Project ID</span>
        <span class="info-value mono">{{ project.id }}</span>
      </div>
      <div class="info-item">
        <span class="info-label">Status</span>
        <span class="info-value">{{ project.status }}</span>
      </div>
      <div v-if="project.product_name" class="info-item">
        <span class="info-label">Product</span>
        <span class="info-value">{{ project.product_name }}</span>
      </div>
      <div class="info-item">
        <span class="info-label">Teams</span>
        <span class="info-value">{{ totalTeamCount }} assigned</span>
      </div>
      <div v-if="project.created_at" class="info-item">
        <span class="info-label">Created</span>
        <span class="info-value">{{ new Date(project.created_at).toLocaleDateString() }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card {
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

/* GitHub */
.github-content {
  padding: 20px;
}

.github-link {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  color: var(--text-primary);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  transition: all 0.2s;
}

.github-link:hover {
  background: var(--bg-tertiary);
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.github-link svg {
  flex-shrink: 0;
}

.github-link .external-icon {
  width: 14px;
  height: 14px;
  color: var(--text-tertiary);
}

/* Info Grid */
.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  padding: 20px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-value {
  font-size: 0.9rem;
  color: var(--text-primary);
}

.info-value.mono {
  font-family: var(--font-mono);
  font-size: 0.8rem;
}
</style>
