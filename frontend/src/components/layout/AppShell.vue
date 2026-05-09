<script setup lang="ts">
/**
 * Main app shell extracted from App.vue (v0.7.5d).
 *
 * Renders the header, optional API-key banner, sidebar, mobile drawer
 * affordances, and the `<main>` content area. The router-view is
 * passed in via the default slot so App.vue retains control over the
 * `<router-view />` placement and ErrorBoundary wiring.
 *
 * App.vue stays the source of truth for:
 *   - the outer `.app-layout` container + welcome-page conditional
 *   - the toast/tour overlays (siblings of this shell)
 *   - all `provide()` calls
 *
 * Styles for `.sidebar`, `.collapse-toggle`, `.main-content`, etc. are
 * defined globally in App.vue and remain unchanged.
 */
import AppHeader from './AppHeader.vue';
import AppSidebar from './AppSidebar.vue';
import ApiKeyBanner from './ApiKeyBanner.vue';
import type { Trigger, Product, Project, Team, Plugin, AIBackend } from '../../services/api';

defineProps<{
  // Sidebar collapse / mobile drawer state
  isCollapsed: boolean;
  isMobile: boolean;
  isMobileOpen: boolean;

  // Sidebar data
  appVersion: string;
  healthColor: string;
  healthTooltip: string;
  activeExecutionCount: number;
  customTriggers: Trigger[];
  products: Product[];
  projects: Project[];
  teams: Team[];
  plugins: Plugin[];
  sidebarBackends: AIBackend[];
  sidebarLoading: boolean;
  sidebarErrors: Record<string, string | null>;

  // Banner / layout
  showApiKeyBanner: boolean;
  isFullBleed: boolean;
}>();

defineEmits<{
  (e: 'toggle-sidebar'): void;
  (e: 'toggle-collapse'): void;
  (e: 'close-mobile'): void;
  (e: 'authenticated'): void;
  (e: 'retry-sidebar-section', section: string): void;
}>();
</script>

<template>
  <AppHeader @toggle-sidebar="$emit('toggle-sidebar')" />

  <ApiKeyBanner
    v-if="showApiKeyBanner"
    @authenticated="$emit('authenticated')"
  />

  <div class="app-body">
    <!-- Mobile backdrop overlay -->
    <div v-if="isMobile && isMobileOpen" class="sidebar-backdrop" @click="$emit('close-mobile')"></div>

    <!-- Desktop collapse toggle -->
    <button
      v-if="!isMobile"
      class="collapse-toggle"
      :aria-label="isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      :aria-expanded="!isCollapsed"
      aria-controls="app-sidebar-nav"
      @click="$emit('toggle-collapse')"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline v-if="isCollapsed" points="9,18 15,12 9,6"/>
        <polyline v-else points="15,18 9,12 15,6"/>
      </svg>
    </button>

    <AppSidebar
      :app-version="appVersion"
      :health-color="healthColor"
      :health-tooltip="healthTooltip"
      :active-execution-count="activeExecutionCount"
      :custom-triggers="customTriggers"
      :products="products"
      :projects="projects"
      :teams="teams"
      :plugins="plugins"
      :sidebar-backends="sidebarBackends"
      :collapsed="isCollapsed"
      :is-mobile="isMobile"
      :mobile-open="isMobileOpen"
      :sidebar-loading="sidebarLoading"
      :sidebar-errors="sidebarErrors"
      @close-mobile="$emit('close-mobile')"
      @retry-sidebar-section="(section: string) => $emit('retry-sidebar-section', section)"
    />

    <main id="main-content" class="main-content" tabindex="-1">
      <div class="content-wrapper" :class="{ 'full-bleed': isFullBleed }">
        <slot />
      </div>
    </main>
  </div>
</template>
