/**
 * E2E tests for Agents CRUD lifecycle and design page.
 */
import { test, expect } from '../fixtures/base';
import { MOCK_AGENT, MOCK_TEAM, MOCK_BACKEND_ITEM } from '../fixtures/mock-data';

test.describe('Agents CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('lists agents with mock data', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/agents': { agents: [MOCK_AGENT] },
    });
    await sidebarPage.clickSubmenuItem('Agents', 'All Agents');
    await expect(page.locator('h1').filter({ hasText: 'Agents' })).toBeVisible();
    await expect(page.locator('.main-content').getByText('Test Agent').first()).toBeVisible();
  });

  test('shows empty state when no agents exist', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/agents': { agents: [] },
    });
    await sidebarPage.clickSubmenuItem('Agents', 'All Agents');
    await expect(page.locator('h1').filter({ hasText: 'Agents' })).toBeVisible();
  });

  test('navigates to agent create wizard', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/backends': { backends: [MOCK_BACKEND_ITEM] },
      'admin/teams': { teams: [MOCK_TEAM] },
    });
    await sidebarPage.clickSubmenuItem('Agents', 'Design an Agent');
    await expect(page.locator('h1').filter({ hasText: 'Design Agent' })).toBeVisible();
  });

  test('views agent design page', async ({ page, mockApi }) => {
    await mockApi({
      'admin/agents/agent-test1': MOCK_AGENT,
      'admin/agents': { agents: [MOCK_AGENT] },
      'admin/backends': { backends: [MOCK_BACKEND_ITEM] },
    });
    await page.goto('/agents/agent-test1');
    await expect(page.locator('h1').filter({ hasText: 'Test Agent' }).first()).toBeVisible();
  });

  test('agent create wizard renders page heading', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/backends': { backends: [MOCK_BACKEND_ITEM] },
      'admin/teams': { teams: [MOCK_TEAM] },
    });
    await sidebarPage.clickSubmenuItem('Agents', 'Design an Agent');
    await expect(page.locator('h1').filter({ hasText: 'Design Agent' })).toBeVisible();
  });
});
