/**
 * Extended Playwright test fixture with global API mocking and shared fixtures.
 *
 * Every test automatically gets:
 * - All 8 mandatory API endpoints mocked (health, version, triggers, projects, products, teams, plugins, backends)
 * - A `sidebarPage` fixture for navigation
 * - A `mockApi` helper for per-test additional API mocking
 */
import { test as base, expect } from '@playwright/test';
import { SidebarPage } from '../pages/sidebar.page';
import {
  MOCK_HEALTH,
  MOCK_VERSION,
  MOCK_TRIGGERS,
  MOCK_PROJECTS,
  MOCK_PRODUCTS,
  MOCK_TEAMS,
  MOCK_PLUGINS,
  MOCK_BACKENDS,
} from './mock-data';

type HiveFixtures = {
  sidebarPage: SidebarPage;
  mockApi: (routes: Record<string, unknown>) => Promise<void>;
};

export const test = base.extend<HiveFixtures>({
  page: async ({ page }, use) => {
    // Mock all initial API calls that App.vue makes on mount.
    // These MUST be set up BEFORE navigating to any page.
    await page.route('**/health/readiness', (route) =>
      route.fulfill({ json: MOCK_HEALTH }),
    );
    await page.route('**/health/liveness', (route) =>
      route.fulfill({ json: { status: 'ok' } }),
    );
    await page.route('**/api/version', (route) =>
      route.fulfill({ json: MOCK_VERSION }),
    );
    await page.route('**/admin/triggers', (route) =>
      route.fulfill({ json: MOCK_TRIGGERS }),
    );
    await page.route('**/admin/projects', (route) =>
      route.fulfill({ json: MOCK_PROJECTS }),
    );
    await page.route('**/admin/products', (route) =>
      route.fulfill({ json: MOCK_PRODUCTS }),
    );
    await page.route('**/admin/teams', (route) =>
      route.fulfill({ json: MOCK_TEAMS }),
    );
    await page.route('**/admin/plugins', (route) =>
      route.fulfill({ json: MOCK_PLUGINS }),
    );
    await page.route('**/admin/backends', (route) =>
      route.fulfill({ json: MOCK_BACKENDS }),
    );

    await use(page);
  },

  sidebarPage: async ({ page }, use) => {
    await use(new SidebarPage(page));
  },

  mockApi: async ({ page }, use) => {
    const mock = async (routes: Record<string, unknown>) => {
      for (const [pattern, response] of Object.entries(routes)) {
        await page.route(`**/${pattern}`, (route) =>
          route.fulfill({ json: response }),
        );
      }
    };
    await use(mock);
  },
});

export { expect };
