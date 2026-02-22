/**
 * E2E tests for Skills explore, install, library, playground, and create wizard.
 */
import { test, expect } from '../fixtures/base';
import { MOCK_SKILL } from '../fixtures/mock-data';

test.describe('Skills', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('navigates to Skills Playground', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Skills', 'Playground');
    await expect(page.locator('h1').filter({ hasText: 'Skills Playground' })).toBeVisible();
  });

  test('navigates to Skill Library', async ({ page, sidebarPage, mockApi }) => {
    // MySkills calls skillsApi.list() -> /api/skills/ and userSkillsApi.list() -> /api/skills/user
    await page.route('**/api/skills/user', (route) =>
      route.fulfill({ json: { skills: [MOCK_SKILL] } }),
    );
    await page.route('**/api/skills/', (route) =>
      route.fulfill({ json: { skills: [] } }),
    );
    await sidebarPage.clickSubmenuItem('Skills', 'Skill Library');
    await expect(page.locator('h1').filter({ hasText: 'Skill Library' })).toBeVisible();
  });

  test('shows empty skill library', async ({ page, sidebarPage }) => {
    await page.route('**/api/skills/user', (route) =>
      route.fulfill({ json: { skills: [] } }),
    );
    await page.route('**/api/skills/', (route) =>
      route.fulfill({ json: { skills: [] } }),
    );
    await sidebarPage.clickSubmenuItem('Skills', 'Skill Library');
    await expect(page.locator('h1').filter({ hasText: 'Skill Library' })).toBeVisible();
  });

  test('browses Explore Skills page', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/marketplaces': { marketplaces: [] },
    });
    await page.route('**/admin/marketplaces/search*', (route) =>
      route.fulfill({ json: { results: [] } }),
    );
    await page.route('**/api/skills/skills-sh/search*', (route) =>
      route.fulfill({ json: { results: [], npx_available: true } }),
    );
    await sidebarPage.clickSubmenuItem('Skills', 'Explore');
    await expect(page.locator('h1').filter({ hasText: 'Explore Skills' })).toBeVisible();
  });

  test('navigates to Design a Skill wizard', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Skills', 'Design a Skill');
    await expect(page.locator('h1').filter({ hasText: 'Design a Skill' })).toBeVisible();
  });

  test('views skill detail via deep link', async ({ page }) => {
    // SkillDetailPage calls userSkillsApi.list() -> /api/skills/user
    await page.route('**/api/skills/user', (route) =>
      route.fulfill({ json: { skills: [MOCK_SKILL] } }),
    );
    await page.goto('/skills/1');
    await expect(page.locator('.main-content').getByText('test-skill').first()).toBeVisible();
  });
});
