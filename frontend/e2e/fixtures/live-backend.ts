/**
 * Live-backend test fixture — NO API mocking.
 * All API calls hit the real backend started by playwright.config.ts webServer.
 * Use this for integration tests that verify full-stack data flow.
 *
 * Unlike the base fixture (base.ts) which sets up page.route() interceptors
 * for all mandatory endpoints, this fixture lets every request through to
 * the actual backend. This catches contract mismatches between frontend
 * TypeScript types and backend JSON responses.
 */
import { test as base, expect } from '@playwright/test';
import { SidebarPage } from '../pages/sidebar.page';

type LiveFixtures = {
  sidebarPage: SidebarPage;
};

export const test = base.extend<LiveFixtures>({
  sidebarPage: async ({ page }, use) => {
    await use(new SidebarPage(page));
  },
});

export { expect };
