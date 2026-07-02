import type { RouteRecordRaw } from 'vue-router';

export const authRoutes: RouteRecordRaw[] = [
  // Welcome & Setup
  {
    path: '/welcome',
    name: 'welcome',
    component: () => import('../../views/WelcomePage.vue'),
    meta: { title: 'Welcome to Agented', fullBleed: true },
  },
  // Login (track B, wave 35)
  {
    path: '/login',
    name: 'login',
    component: () => import('../../views/LoginPage.vue'),
    meta: { title: 'Sign in', fullBleed: true, public: true },
  },
  // Signup (track B, wave 38)
  {
    path: '/signup',
    name: 'signup',
    component: () => import('../../views/SignupPage.vue'),
    meta: { title: 'Create account', fullBleed: true, public: true },
  },
  // Forgot/reset password (track B, wave 44)
  {
    path: '/forgot-password',
    name: 'forgot-password',
    component: () => import('../../views/ForgotPasswordPage.vue'),
    meta: { title: 'Forgot password', fullBleed: true, public: true },
  },
  {
    path: '/reset-password',
    name: 'reset-password',
    component: () => import('../../views/ResetPasswordPage.vue'),
    meta: { title: 'Reset password', fullBleed: true, public: true },
  },
  // Phase 25: live-share — a teammate attaches a shared session by URL token.
  // Public: the scoped share token IS the credential (no login required).
  {
    path: '/shared/:token',
    name: 'shared-session',
    component: () => import('../../views/SharedSessionView.vue'),
    meta: { title: 'Shared session', fullBleed: true, public: true },
  },
  // API Key-Based Programmatic Access (Feature 38)
  {
    path: '/settings/api-keys',
    name: 'api-keys',
    component: () => import('../../views/ApiKeysPage.vue'),
    meta: { title: 'API Keys' },
  },
  // RBAC Settings
  {
    path: '/settings/rbac',
    name: 'rbac-settings',
    component: () => import('../../views/RbacSettingsPage.vue'),
    meta: { title: 'RBAC Settings' },
  },
];
