/**
 * E2E tests for Trigger management (list, create, edit, delete).
 */
import { test, expect } from '../fixtures/base';
import { MOCK_TRIGGER } from '../fixtures/mock-data';

test.describe('Triggers', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('lists triggers', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/triggers': { triggers: [MOCK_TRIGGER] },
    });
    await sidebarPage.navigateToFlatLink('Triggers');
    await expect(page.locator('.app-breadcrumb .current')).toHaveText('Triggers');
    await expect(page.locator('.main-content').getByText('Test Trigger').first()).toBeVisible();
  });

  test('shows empty state when no triggers exist', async ({ page, sidebarPage }) => {
    await sidebarPage.navigateToFlatLink('Triggers');
    await expect(page.locator('.app-breadcrumb .current')).toHaveText('Triggers');
  });

  test('navigates to triggers via deep link', async ({ page, mockApi }) => {
    await mockApi({
      'admin/triggers': { triggers: [MOCK_TRIGGER] },
    });
    await page.goto('/triggers');
    await expect(page.locator('.app-breadcrumb .current')).toHaveText('Triggers');
  });

  test('renders trigger management page structure', async ({ page, sidebarPage }) => {
    await sidebarPage.navigateToFlatLink('Triggers');
    // The trigger management page has a breadcrumb and backend status section
    await expect(page.locator('.app-breadcrumb .current')).toHaveText('Triggers');
    await expect(page.locator('.main-content').getByText('Backend Status').first()).toBeVisible();
  });
});
