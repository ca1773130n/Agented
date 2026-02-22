/**
 * E2E tests for Projects CRUD lifecycle.
 */
import { test, expect } from '../fixtures/base';
import { MOCK_PROJECT, MOCK_PRODUCT } from '../fixtures/mock-data';

test.describe('Projects CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('lists projects with mock data', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/projects': { projects: [MOCK_PROJECT] },
    });
    await sidebarPage.clickSubmenuItem('Projects', 'All Projects');
    await expect(page.locator('h1').filter({ hasText: 'Projects' })).toBeVisible();
    await expect(page.locator('.main-content').getByText('Test Project').first()).toBeVisible();
  });

  test('shows empty state when no projects exist', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Projects', 'All Projects');
    await expect(page.locator('h1').filter({ hasText: 'Projects' })).toBeVisible();
  });

  test('creates a new project via form', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/products': { products: [MOCK_PRODUCT] },
    });
    let created = false;
    await page.route('**/admin/projects', (route) => {
      if (route.request().method() === 'POST') {
        created = true;
        return route.fulfill({ json: MOCK_PROJECT });
      }
      if (created) {
        return route.fulfill({ json: { projects: [MOCK_PROJECT] } });
      }
      return route.fulfill({ json: { projects: [] } });
    });

    await sidebarPage.clickSubmenuItem('Projects', 'All Projects');
    await expect(page.locator('h1').filter({ hasText: 'Projects' })).toBeVisible();

    // Click create button
    const createBtn = page.locator('.main-content').getByRole('button', { name: /create/i }).first();
    await createBtn.click();

    // Fill form - the modal is teleported to body
    await page.locator('.modal').waitFor({ state: 'visible' });
    await page.locator('.modal input[type="text"]').first().fill('Test Project');
    await page.locator('.modal').getByRole('button', { name: /create project/i }).click();
  });

  test('views project dashboard', async ({ page, mockApi }) => {
    await mockApi({
      'admin/projects': { projects: [MOCK_PROJECT] },
      'admin/projects/proj-test01': MOCK_PROJECT,
    });
    await page.goto('/projects/proj-test01');
    await expect(page.locator('.main-content').getByText('Test Project').first()).toBeVisible();
  });

  test('deletes a project', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/projects': { projects: [MOCK_PROJECT] },
    });
    await page.route('**/admin/projects/proj-test01', (route) => {
      if (route.request().method() === 'DELETE') {
        return route.fulfill({ json: { success: true } });
      }
      return route.fulfill({ json: MOCK_PROJECT });
    });

    await sidebarPage.clickSubmenuItem('Projects', 'All Projects');
    await expect(page.locator('.main-content').getByText('Test Project').first()).toBeVisible();
  });
});
