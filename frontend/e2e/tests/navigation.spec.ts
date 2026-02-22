/**
 * E2E tests for sidebar navigation across all 14 expandable sections.
 * Verifies that clicking sidebar items renders the correct views and updates URLs.
 */
import { test, expect } from '../fixtures/base';

test.describe('Sidebar Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('navigates through all Dashboard sub-items', async ({ page, sidebarPage }) => {
    // All Dashboards
    await sidebarPage.clickSubmenuItem('Dashboards', 'All Dashboards');
    await expect(page.getByText('Command Center')).toBeVisible();

    // Security Scan
    await sidebarPage.clickSubmenuItem('Dashboards', 'Security Scan');
    await expect(page.locator('.app-breadcrumb .current')).toHaveText('Security Scan');

    // PR Review
    await sidebarPage.clickSubmenuItem('Dashboards', 'PR Review');
    await expect(page.locator('.app-breadcrumb .current')).toHaveText('PR Review');

    // Token Usage
    await sidebarPage.clickSubmenuItem('Dashboards', 'Token Usage');
    await expect(page.locator('h1').filter({ hasText: 'Token Usage' })).toBeVisible();
  });

  test('navigates through Dashboard summary pages', async ({ page, sidebarPage, mockApi }) => {
    // We need to add dashboard summary items to the sidebar.
    // These appear under Dashboards but are not in the sidebar by default --
    // they are direct-linked from the All Dashboards page. We navigate via URL.
    await page.goto('/dashboards/products');
    await expect(page.locator('h1').filter({ hasText: 'Products Overview' })).toBeVisible();

    await page.goto('/dashboards/projects');
    await expect(page.locator('h1').filter({ hasText: 'Projects Overview' })).toBeVisible();

    await page.goto('/dashboards/teams');
    await expect(page.locator('h1').filter({ hasText: 'Teams Overview' })).toBeVisible();

    await page.goto('/dashboards/agents');
    await expect(page.locator('h1').filter({ hasText: 'Agents Overview' })).toBeVisible();
  });

  test('navigates through AI Backends sub-items', async ({ page, sidebarPage }) => {
    // All Backends
    await sidebarPage.clickSubmenuItem('AI Backends', 'All Backends');
    await expect(page.locator('h1').filter({ hasText: 'AI Backends' })).toBeVisible();

    // Accounts (Service Health)
    await sidebarPage.clickSubmenuItem('AI Backends', 'Accounts');
    await expect(page.locator('h1').filter({ hasText: 'Accounts' })).toBeVisible();
  });

  test('navigates through Products section', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Products', 'All Products');
    await expect(page.locator('h1').filter({ hasText: 'Products' })).toBeVisible();
  });

  test('navigates through Projects section', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Projects', 'All Projects');
    await expect(page.locator('h1').filter({ hasText: 'Projects' })).toBeVisible();
  });

  test('navigates through Teams section', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Teams', 'All Teams');
    await expect(page.locator('h1').filter({ hasText: 'Teams' })).toBeVisible();
  });

  test('navigates through Agents section', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Agents', 'All Agents');
    await expect(page.locator('h1').filter({ hasText: 'Agents' })).toBeVisible();

    await sidebarPage.clickSubmenuItem('Agents', 'Design an Agent');
    await expect(page.locator('h1').filter({ hasText: 'Design Agent' })).toBeVisible();
  });

  test('navigates to Triggers (flat link)', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/triggers': { triggers: [] },
      'api/bots/status': { bots: [] },
    });
    // Triggers is under "Tools" section label, but it's a flat link (not expandable)
    await sidebarPage.navigateToFlatLink('Triggers');
    await expect(page.locator('.app-breadcrumb .current')).toHaveText('Triggers');
  });

  test('navigates through Plugins section', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Plugins', 'All Plugins');
    await expect(page.locator('h1').filter({ hasText: 'Plugins' })).toBeVisible();

    await sidebarPage.clickSubmenuItem('Plugins', 'Design a Plugin');
    await expect(page.locator('h1').filter({ hasText: 'Design a Plugin' })).toBeVisible();

    await sidebarPage.clickSubmenuItem('Plugins', 'Explore');
    await expect(page.locator('h1').filter({ hasText: 'Explore Plugins' })).toBeVisible();

    await sidebarPage.clickSubmenuItem('Plugins', 'Harness Integration');
    await expect(page.locator('h1').filter({ hasText: 'Harness Integration' })).toBeVisible();
  });

  test('navigates through Skills section', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Skills', 'Playground');
    await expect(page.locator('h1').filter({ hasText: 'Skills Playground' })).toBeVisible();

    await sidebarPage.clickSubmenuItem('Skills', 'Design a Skill');
    await expect(page.locator('h1').filter({ hasText: 'Design a Skill' })).toBeVisible();

    await sidebarPage.clickSubmenuItem('Skills', 'Skill Library');
    await expect(page.locator('h1').filter({ hasText: 'Skill Library' })).toBeVisible();

    await sidebarPage.clickSubmenuItem('Skills', 'Explore');
    await expect(page.locator('h1').filter({ hasText: 'Explore Skills' })).toBeVisible();
  });

  test('navigates through Commands section', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Commands', 'All Commands');
    await expect(page.locator('h1').filter({ hasText: 'Commands' })).toBeVisible();

    await sidebarPage.clickSubmenuItem('Commands', 'Design a Command');
    await expect(page.locator('h1').filter({ hasText: 'Design a Command' })).toBeVisible();
  });

  test('navigates through Hooks section', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Hooks', 'All Hooks');
    await expect(page.locator('h1').filter({ hasText: 'Hooks' })).toBeVisible();

    await sidebarPage.clickSubmenuItem('Hooks', 'Design a Hook');
    await expect(page.locator('h1').filter({ hasText: 'Design a Hook' })).toBeVisible();
  });

  test('navigates through Rules section', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Rules', 'All Rules');
    await expect(page.locator('h1').filter({ hasText: 'Rules' })).toBeVisible();

    await sidebarPage.clickSubmenuItem('Rules', 'Design a Rule');
    await expect(page.locator('h1').filter({ hasText: 'Design a Rule' })).toBeVisible();
  });

  test('navigates to Settings (flat link)', async ({ page, sidebarPage }) => {
    await sidebarPage.navigateToFlatLink('Settings');
    await expect(page.locator('h1').filter({ hasText: 'Settings' })).toBeVisible();
  });

  test('URL updates correctly on navigation', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Products', 'All Products');
    await expect(page).toHaveURL(/\/products$/);

    await sidebarPage.clickSubmenuItem('Teams', 'All Teams');
    await expect(page).toHaveURL(/\/teams$/);

    await sidebarPage.clickSubmenuItem('Agents', 'All Agents');
    await expect(page).toHaveURL(/\/agents$/);

    await sidebarPage.clickSubmenuItem('Skills', 'Skill Library');
    await expect(page).toHaveURL(/\/skills$/);

    await sidebarPage.navigateToFlatLink('Settings');
    await expect(page).toHaveURL(/\/settings$/);
  });

  test('deep link navigation works', async ({ page }) => {
    await page.goto('/products');
    await expect(page.locator('h1').filter({ hasText: 'Products' })).toBeVisible();

    await page.goto('/teams');
    await expect(page.locator('h1').filter({ hasText: 'Teams' })).toBeVisible();

    await page.goto('/settings');
    await expect(page.locator('h1').filter({ hasText: 'Settings' })).toBeVisible();

    await page.goto('/backends');
    await expect(page.locator('h1').filter({ hasText: 'AI Backends' })).toBeVisible();
  });
});
