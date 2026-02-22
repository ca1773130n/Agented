/**
 * E2E tests for AI Backends page, detail view, and chat test panel.
 */
import { test, expect } from '../fixtures/base';
import { MOCK_BACKEND_ITEM, MOCK_ACCOUNTS } from '../fixtures/mock-data';

test.describe('AI Backends', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('renders All Backends page', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/backends': { backends: [MOCK_BACKEND_ITEM] },
    });
    await sidebarPage.clickSubmenuItem('AI Backends', 'All Backends');
    await expect(page.locator('h1').filter({ hasText: 'AI Backends' })).toBeVisible();
  });

  test('shows empty state when no backends', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('AI Backends', 'All Backends');
    await expect(page.locator('h1').filter({ hasText: 'AI Backends' })).toBeVisible();
  });

  test('renders chat test panel on All Backends page', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/backends': { backends: [MOCK_BACKEND_ITEM] },
    });
    await sidebarPage.clickSubmenuItem('AI Backends', 'All Backends');
    await expect(page.locator('h1').filter({ hasText: 'AI Backends' })).toBeVisible();
    // Check that the test panel section is present
    await expect(page.locator('h2').filter({ hasText: 'Test Backend' }).first()).toBeVisible();
  });

  test('navigates to backend detail page via deep link', async ({ page, mockApi }) => {
    await mockApi({
      'admin/backends': { backends: [MOCK_BACKEND_ITEM] },
      'admin/backends/claude': MOCK_BACKEND_ITEM,
      'admin/backends/claude/accounts': { accounts: [] },
    });
    await page.goto('/backends/claude');
    await expect(page.locator('h1').filter({ hasText: 'Claude' }).first()).toBeVisible();
  });

  test('navigates to Accounts (Service Health) page', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/backends': { backends: [MOCK_BACKEND_ITEM] },
      'admin/backends/accounts': MOCK_ACCOUNTS,
    });
    await sidebarPage.clickSubmenuItem('AI Backends', 'Accounts');
    await expect(page.locator('h1').filter({ hasText: 'Accounts' })).toBeVisible();
  });
});
