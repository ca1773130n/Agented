/**
 * E2E tests for Rules list and design page.
 */
import { test, expect } from '../fixtures/base';
import { MOCK_RULE } from '../fixtures/mock-data';

test.describe('Rules', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('lists rules', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/rules': { rules: [MOCK_RULE] },
    });
    await sidebarPage.clickSubmenuItem('Rules', 'All Rules');
    await expect(page.locator('h1').filter({ hasText: 'Rules' })).toBeVisible();
    await expect(page.locator('.main-content').getByText('test-rule').first()).toBeVisible();
  });

  test('shows empty state when no rules exist', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/rules': { rules: [] },
    });
    await sidebarPage.clickSubmenuItem('Rules', 'All Rules');
    await expect(page.locator('h1').filter({ hasText: 'Rules' })).toBeVisible();
  });

  test('navigates to rule design page', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Rules', 'Design a Rule');
    await expect(page.locator('h1').filter({ hasText: 'Design a Rule' })).toBeVisible();
  });

  test('navigates to rules via deep link', async ({ page, mockApi }) => {
    await mockApi({
      'admin/rules': { rules: [MOCK_RULE] },
    });
    await page.goto('/rules');
    await expect(page.locator('h1').filter({ hasText: 'Rules' })).toBeVisible();
  });
});
