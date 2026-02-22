/**
 * Integration tests for entity CRUD flows — live backend, NO API mocking.
 *
 * These tests create real entities via the API, then navigate to the frontend
 * to verify the data appears correctly in the UI. This catches contract
 * mismatches between API responses and frontend rendering expectations.
 */
import { test, expect } from '../../fixtures/live-backend';

test.describe('Entity CRUD Flow (live backend)', () => {
  test.describe.configure({ mode: 'serial' });

  let createdAgentId: string | null = null;
  let createdTeamId: string | null = null;

  test.beforeAll(async ({ request }) => {
    const response = await request.get('/health/readiness');
    expect(response.status()).toBe(200);
  });

  test('creates an agent via API and verifies it appears in list', async ({ page, sidebarPage }) => {
    // Create agent via API
    const createResponse = await page.request.post('/admin/agents', {
      data: {
        name: 'E2E Test Agent',
        role: 'tester',
        backend_type: 'claude',
      },
    });
    expect(createResponse.status()).toBe(200);
    const createData = await createResponse.json();
    createdAgentId = createData.agent_id || createData.id || null;

    // Navigate to app and then to agents list
    await page.goto('/');
    await sidebarPage.clickSubmenuItem('Agents', 'All Agents');

    // Verify the created agent appears in the list
    await expect(page.locator('text=E2E Test Agent')).toBeVisible();
  });

  test('creates a team via API and verifies it appears in list', async ({ page, sidebarPage }) => {
    // Create team via API
    const createResponse = await page.request.post('/admin/teams', {
      data: {
        name: 'E2E Test Team',
      },
    });
    expect(createResponse.status()).toBe(200);
    const createData = await createResponse.json();
    createdTeamId = createData.team_id || createData.id || null;

    // Navigate to app and then to teams list
    await page.goto('/');
    await sidebarPage.clickSubmenuItem('Teams', 'All Teams');

    // Verify the created team appears in the list
    await expect(page.locator('text=E2E Test Team')).toBeVisible();
  });

  test('trigger detail page loads without error', async ({ page, sidebarPage }) => {
    // Navigate to app
    await page.goto('/');

    // Navigate to triggers list via flat link
    await sidebarPage.navigateToFlatLink('Triggers');

    // Verify the page loaded without error
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });

  test('trigger list shows predefined triggers', async ({ page, sidebarPage }) => {
    await page.goto('/');

    // Navigate to triggers
    await sidebarPage.navigateToFlatLink('Triggers');

    // Verify both predefined triggers appear
    await expect(page.locator('text=Security Scan')).toBeVisible();
    await expect(page.locator('text=PR Review')).toBeVisible();
  });

  test.afterAll(async ({ request }) => {
    // Best-effort cleanup of created entities
    if (createdAgentId) {
      await request.delete(`/admin/agents/${createdAgentId}`).catch(() => {});
    }
    if (createdTeamId) {
      await request.delete(`/admin/teams/${createdTeamId}`).catch(() => {});
    }
  });
});
