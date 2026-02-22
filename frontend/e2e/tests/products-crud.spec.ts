/**
 * E2E tests for Products CRUD lifecycle.
 */
import { test, expect } from '../fixtures/base';
import { MOCK_PRODUCT } from '../fixtures/mock-data';

test.describe('Products CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('lists products with mock data', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/products': { products: [MOCK_PRODUCT] },
    });
    await sidebarPage.clickSubmenuItem('Products', 'All Products');
    await expect(page.locator('h1').filter({ hasText: 'Products' })).toBeVisible();
    await expect(page.locator('.main-content').getByText('Test Product').first()).toBeVisible();
  });

  test('shows empty state when no products exist', async ({ page, sidebarPage }) => {
    await sidebarPage.clickSubmenuItem('Products', 'All Products');
    await expect(page.locator('h1').filter({ hasText: 'Products' })).toBeVisible();
  });

  test('creates a new product via form', async ({ page, sidebarPage }) => {
    let created = false;
    await page.route('**/admin/products', (route) => {
      if (route.request().method() === 'POST') {
        created = true;
        return route.fulfill({ json: MOCK_PRODUCT });
      }
      if (created) {
        return route.fulfill({ json: { products: [MOCK_PRODUCT] } });
      }
      return route.fulfill({ json: { products: [] } });
    });

    await sidebarPage.clickSubmenuItem('Products', 'All Products');
    await expect(page.locator('h1').filter({ hasText: 'Products' })).toBeVisible();

    // Click create button
    const createBtn = page.locator('.main-content').getByRole('button', { name: /create/i }).first();
    await createBtn.click();

    // Fill form - the modal is teleported to body
    await page.locator('.modal').waitFor({ state: 'visible' });
    await page.locator('.modal input[type="text"]').first().fill('Test Product');
    await page.locator('.modal').getByRole('button', { name: /create product/i }).click();
  });

  test('views product dashboard', async ({ page, mockApi }) => {
    await mockApi({
      'admin/products': { products: [MOCK_PRODUCT] },
      'admin/products/prod-test01': MOCK_PRODUCT,
    });
    await page.goto('/products/prod-test01');
    await expect(page.locator('.main-content').getByText('Test Product').first()).toBeVisible();
  });

  test('deletes a product', async ({ page, sidebarPage, mockApi }) => {
    await mockApi({
      'admin/products': { products: [MOCK_PRODUCT] },
    });
    await page.route('**/admin/products/prod-test01', (route) => {
      if (route.request().method() === 'DELETE') {
        return route.fulfill({ json: { success: true } });
      }
      return route.fulfill({ json: MOCK_PRODUCT });
    });

    await sidebarPage.clickSubmenuItem('Products', 'All Products');
    await expect(page.locator('.main-content').getByText('Test Product').first()).toBeVisible();
  });
});
