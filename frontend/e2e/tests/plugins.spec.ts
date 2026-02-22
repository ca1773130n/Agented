/**
 * E2E tests for Plugins CRUD, marketplace explore, and design.
 */
import { test, expect } from '../fixtures/base';
import { MOCK_PLUGIN } from '../fixtures/mock-data';

test.describe('Plugins', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('lists plugins with mock data', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/plugins': { plugins: [MOCK_PLUGIN] },
    });
    await sidebarPage.clickSubmenuItem('Plugins', 'All Plugins');
    await expect(page.locator('h1').filter({ hasText: 'Plugins' })).toBeVisible();
    await expect(page.locator('.main-content').getByText('Test Plugin').first()).toBeVisible();
  });

  test('shows empty state when no plugins exist', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Plugins', 'All Plugins');
    await expect(page.locator('h1').filter({ hasText: 'Plugins' })).toBeVisible();
  });

  test('navigates to plugin design page', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Plugins', 'Design a Plugin');
    await expect(page.locator('h1').filter({ hasText: 'Design a Plugin' })).toBeVisible();
  });

  test('browses marketplace explore page', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/marketplaces': { marketplaces: [] },
      'admin/marketplaces/search': { results: [] },
    });
    // Also mock the skills.sh search endpoint
    await page.route('**/api/skills/skills-sh/search*', (route) =>
      route.fulfill({ json: { results: [], npx_available: true } }),
    );
    await sidebarPage.clickSubmenuItem('Plugins', 'Explore');
    await expect(page.locator('h1').filter({ hasText: 'Explore Plugins' })).toBeVisible();
  });

  test('views plugin detail page', async ({ page, mockApi }) => {
    await mockApi({
      'admin/plugins': { plugins: [MOCK_PLUGIN] },
      'admin/plugins/plug-test01': {
        ...MOCK_PLUGIN,
        skills: [],
        hooks: [],
        commands: [],
        rules: [],
        agents: [],
      },
    });
    await page.goto('/plugins/plug-test01');
    await expect(page.locator('.main-content').getByText('Test Plugin').first()).toBeVisible();
  });

  test('navigates to harness integration', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/settings/harness': { harness_root: '', claude_config_dir: '' },
    });
    await sidebarPage.clickSubmenuItem('Plugins', 'Harness Integration');
    await expect(page.locator('h1').filter({ hasText: 'Harness Integration' })).toBeVisible();
  });
});
