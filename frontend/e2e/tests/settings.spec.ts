/**
 * E2E tests for Settings page.
 */
import { test, expect } from '../fixtures/base';

test.describe('Settings', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('renders settings page', async ({ page, sidebarPage }) => {
    await sidebarPage.navigateToFlatLink('Settings');
    await expect(page.locator('h1').filter({ hasText: 'Settings' })).toBeVisible();
  });

  test('displays version information', async ({ page, sidebarPage }) => {
    await sidebarPage.navigateToFlatLink('Settings');
    await expect(page.locator('h1').filter({ hasText: 'Settings' })).toBeVisible();
    // The version is displayed in the sidebar header, not on settings page
    await expect(page.locator('.version-tag')).toHaveText('0.2.2');
  });

  test('navigates to settings via deep link', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.locator('h1').filter({ hasText: 'Settings' })).toBeVisible();
  });

  test('settings page structure renders correctly', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/settings': { settings: {} },
      'admin/marketplaces': { marketplaces: [] },
    });
    await sidebarPage.navigateToFlatLink('Settings');
    await expect(page.locator('h1').filter({ hasText: 'Settings' })).toBeVisible();
  });
});
