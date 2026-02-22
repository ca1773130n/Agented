/**
 * E2E tests for Dashboard views and summary dashboards.
 */
import { test, expect } from '../fixtures/base';

test.describe('Dashboards', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('renders All Dashboards index with Command Center', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Dashboards', 'All Dashboards');
    await expect(page.getByText('Command Center')).toBeVisible();
  });

  test('navigates to Security Dashboard', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'api/audit/summary': {
        total_audits: 5,
        total_findings: 12,
        projects_scanned: 3,
        severity_breakdown: { critical: 1, high: 3, medium: 5, low: 3 },
        recent_audits: [],
      },
    });
    await sidebarPage.clickSubmenuItem('Dashboards', 'Security Scan');
    await expect(page.locator('.app-breadcrumb .current')).toHaveText('Security Scan');
  });

  test('navigates to PR Review Dashboard', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'api/pr-reviews/summary': {
        total_reviews: 10,
        recent_reviews: [],
      },
    });
    await sidebarPage.clickSubmenuItem('Dashboards', 'PR Review');
    await expect(page.locator('.app-breadcrumb .current')).toHaveText('PR Review');
  });

  test('navigates to Token Usage Dashboard', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/budget/limits': { limits: [] },
      'admin/budget/usage': { usage: [] },
      'admin/budget/history': { history: [] },
    });
    await sidebarPage.clickSubmenuItem('Dashboards', 'Token Usage');
    await expect(page.locator('h1').filter({ hasText: 'Token Usage' })).toBeVisible();
  });

  test('renders entity summary dashboards via deep links', async ({ page }) => {
    await page.goto('/dashboards/products');
    await expect(page.locator('h1').filter({ hasText: 'Products Overview' })).toBeVisible();

    await page.goto('/dashboards/projects');
    await expect(page.locator('h1').filter({ hasText: 'Projects Overview' })).toBeVisible();

    await page.goto('/dashboards/teams');
    await expect(page.locator('h1').filter({ hasText: 'Teams Overview' })).toBeVisible();

    await page.goto('/dashboards/agents');
    await expect(page.locator('h1').filter({ hasText: 'Agents Overview' })).toBeVisible();
  });
});
