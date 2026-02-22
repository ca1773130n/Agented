/**
 * E2E tests for Hooks list and design page.
 */
import { test, expect } from '../fixtures/base';
import { MOCK_HOOK } from '../fixtures/mock-data';

test.describe('Hooks', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('lists hooks', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/hooks': { hooks: [MOCK_HOOK] },
    });
    await sidebarPage.clickSubmenuItem('Hooks', 'All Hooks');
    await expect(page.locator('h1').filter({ hasText: 'Hooks' })).toBeVisible();
    await expect(page.locator('.main-content').getByText('test-hook').first()).toBeVisible();
  });

  test('shows empty state when no hooks exist', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/hooks': { hooks: [] },
    });
    await sidebarPage.clickSubmenuItem('Hooks', 'All Hooks');
    await expect(page.locator('h1').filter({ hasText: 'Hooks' })).toBeVisible();
  });

  test('navigates to hook design page', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Hooks', 'Design a Hook');
    await expect(page.locator('h1').filter({ hasText: 'Design a Hook' })).toBeVisible();
  });

  test('navigates to hooks via deep link', async ({ page, mockApi }) => {
    await mockApi({
      'admin/hooks': { hooks: [MOCK_HOOK] },
    });
    await page.goto('/hooks');
    await expect(page.locator('h1').filter({ hasText: 'Hooks' })).toBeVisible();
  });
});
