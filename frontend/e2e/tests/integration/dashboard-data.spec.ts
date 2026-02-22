/**
 * Integration tests for dashboard data loading — live backend, NO API mocking.
 *
 * These tests verify that dashboard pages load real data from the backend
 * and that core list API endpoints return valid JSON responses. This catches
 * issues where pages fail to render with actual backend data despite
 * passing with mocked responses.
 */
import { test, expect } from '../../fixtures/live-backend';

test.describe('Dashboard Data (live backend)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async ({ request }) => {
    const response = await request.get('/health/readiness');
    expect(response.status()).toBe(200);
  });

  test('dashboards page loads with entity counts', async ({ page }) => {
    // Navigate to the main dashboards hub
    await page.goto('/');

    // Verify the page renders without error
    await expect(page.locator('nav.sidebar')).toBeVisible();

    // Check that at least one dashboard card or section is visible
    // The dashboards page shows summary cards for various entity types
    await expect(
      page.locator('.dashboard-card, .summary-card, .stats-grid, .dashboard-grid').first(),
    ).toBeVisible();
  });

  test('API endpoints return valid JSON for dashboard data', async ({ page }) => {
    // Verify all core list endpoints return valid responses
    const endpoints = [
      { url: '/admin/triggers', key: 'triggers' },
      { url: '/admin/agents', key: 'agents' },
      { url: '/admin/teams', key: 'teams' },
      { url: '/admin/products', key: 'products' },
      { url: '/admin/projects', key: 'projects' },
    ];

    for (const endpoint of endpoints) {
      const response = await page.request.get(endpoint.url);
      expect(response.status()).toBe(200);

      const data = await response.json();
      expect(data).toHaveProperty(endpoint.key);
    }
  });

  test('security audit endpoint responds', async ({ page }) => {
    // GET /api/audit/stats — may return 200 with data or 200 with empty stats.
    // The key assertion is that it does NOT return 500.
    const response = await page.request.get('/api/audit/stats');
    expect(response.status()).not.toBe(500);
  });
});
