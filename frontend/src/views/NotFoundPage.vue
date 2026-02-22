<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();

const currentPath = computed(() => window.location.pathname);
</script>

<template>
  <div class="not-found-page">
    <div class="not-found-content">
      <div class="not-found-code">404</div>
      <h1 class="not-found-title">Page Not Found</h1>
      <p class="not-found-message">
        The page you're looking for doesn't exist or has been moved.
        Check the URL or head back to the dashboard.
      </p>
      <div class="not-found-path">
        <code>{{ currentPath }}</code>
      </div>
      <button class="btn btn-primary" @click="router.push({ name: 'dashboards' })">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px;">
          <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
        Go to Dashboard
      </button>
    </div>
  </div>
</template>

<style scoped>
.not-found-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80vh;
  text-align: center;
}

.not-found-content {
  max-width: 480px;
}

.not-found-code {
  font-family: var(--font-mono);
  font-size: 120px;
  font-weight: 700;
  line-height: 1;
  background: linear-gradient(135deg, var(--accent-cyan) 0%, var(--accent-violet) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 16px;
}

.not-found-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px 0;
}

.not-found-message {
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.6;
  margin: 0 0 20px 0;
}

.not-found-path {
  margin-bottom: 24px;
}

.not-found-path code {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 4px 12px;
  border-radius: 4px;
}
</style>
