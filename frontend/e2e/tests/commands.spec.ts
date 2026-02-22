/**
 * E2E tests for Commands list and design page.
 */
import { test, expect } from '../fixtures/base';
import { MOCK_COMMAND } from '../fixtures/mock-data';

test.describe('Commands', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('lists commands', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/commands': { commands: [MOCK_COMMAND] },
    });
    await sidebarPage.clickSubmenuItem('Commands', 'All Commands');
    await expect(page.locator('h1').filter({ hasText: 'Commands' })).toBeVisible();
    await expect(page.locator('.main-content').getByText('test-command').first()).toBeVisible();
  });

  test('shows empty state when no commands exist', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/commands': { commands: [] },
    });
    await sidebarPage.clickSubmenuItem('Commands', 'All Commands');
    await expect(page.locator('h1').filter({ hasText: 'Commands' })).toBeVisible();
  });

  test('navigates to command design page', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Commands', 'Design a Command');
    await expect(page.locator('h1').filter({ hasText: 'Design a Command' })).toBeVisible();
  });

  test('navigates to commands via deep link', async ({ page, mockApi }) => {
    await mockApi({
      'admin/commands': { commands: [MOCK_COMMAND] },
    });
    await page.goto('/commands');
    await expect(page.locator('h1').filter({ hasText: 'Commands' })).toBeVisible();
  });
});
