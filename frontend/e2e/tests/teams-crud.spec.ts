/**
 * E2E tests for Teams CRUD lifecycle and team builder.
 */
import { test, expect } from '../fixtures/base';
import { MOCK_TEAM, MOCK_PROJECT, MOCK_AGENT } from '../fixtures/mock-data';

test.describe('Teams CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('lists teams with mock data', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/teams': { teams: [MOCK_TEAM] },
    });
    await sidebarPage.clickSubmenuItem('Teams', 'All Teams');
    await expect(page.locator('h1').filter({ hasText: 'Teams' })).toBeVisible();
    await expect(page.locator('.main-content').getByText('Test Team').first()).toBeVisible();
  });

  test('shows empty state when no teams exist', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Teams', 'All Teams');
    await expect(page.locator('h1').filter({ hasText: 'Teams' })).toBeVisible();
  });

  test('creates a team via form', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/projects': { projects: [MOCK_PROJECT] },
      'admin/agents': { agents: [] },
    });
    let created = false;
    await page.route('**/admin/teams', (route) => {
      if (route.request().method() === 'POST') {
        created = true;
        return route.fulfill({ json: MOCK_TEAM });
      }
      if (created) {
        return route.fulfill({ json: { teams: [MOCK_TEAM] } });
      }
      return route.fulfill({ json: { teams: [] } });
    });

    await sidebarPage.clickSubmenuItem('Teams', 'All Teams');
    await expect(page.locator('h1').filter({ hasText: 'Teams' })).toBeVisible();

    // Click create button
    const createBtn = page.locator('.main-content').getByRole('button', { name: /create/i }).first();
    await createBtn.click();

    // Fill form - the modal is teleported to body
    await page.locator('.modal').waitFor({ state: 'visible' });
    await page.locator('.modal input[type="text"]').first().fill('Test Team');
    await page.locator('.modal').getByRole('button', { name: /create team/i }).click();
  });

  test('views team dashboard', async ({ page, mockApi }) => {
    await mockApi({
      'admin/teams': { teams: [MOCK_TEAM] },
      'admin/teams/team-test01': { ...MOCK_TEAM, agents: [MOCK_AGENT] },
      'admin/agents': { agents: [MOCK_AGENT] },
    });
    await page.goto('/teams/team-test01');
    await expect(page.locator('.main-content').getByText('Test Team').first()).toBeVisible();
  });

  test('navigates to team builder', async ({ page, mockApi }) => {
    await mockApi({
      'admin/teams': { teams: [MOCK_TEAM] },
      'admin/teams/team-test01': { ...MOCK_TEAM, agents: [MOCK_AGENT] },
      'admin/agents': { agents: [MOCK_AGENT] },
    });
    await page.goto('/teams/team-test01/builder');
    // Team builder renders the team name in a title
    await expect(page.locator('.main-content').getByText('Test Team').first()).toBeVisible();
  });
});
