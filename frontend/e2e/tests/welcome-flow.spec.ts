/**
 * Welcome page bootstrap smoke test.
 *
 * Covers the first-run path that the user lands on with an empty
 * agented.db: hero → "Begin setup" → key generation → copy → continue.
 *
 * The /health/setup endpoint is mocked so this stays a UI smoke test
 * (no backend writes). Other Playwright suites cover real backend flows
 * via the live-backend fixture; this one stays mocked because the path
 * is purely about the Vue state machine (welcome → keygen → copied → /settings).
 */
import { test, expect } from '../fixtures/base';

const MOCK_ADMIN_KEY = 'agnt_e2e_test_key_0123456789abcdef0123456789abcdef0123456789abcd';

test.describe('Welcome flow — bootstrap', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/health/setup', (route) =>
      route.fulfill({
        json: { api_key: MOCK_ADMIN_KEY, role: 'admin' },
      }),
    );
    // The welcome page wipes localStorage on mount; pre-populate nothing.
    await page.addInitScript(() => {
      window.localStorage.clear();
    });
  });

  test('hero → keygen phase reveals the generate-key button', async ({ page }) => {
    await page.goto('/welcome');

    await expect(page.locator('.hero-headline')).toBeVisible();
    await page.locator('.cta-btn').click();

    await expect(page.locator('.keygen-card')).toBeVisible();
    await expect(page.locator('[data-test="generate-key-btn"]')).toBeVisible();
  });

  test('generates and renders the admin key', async ({ page }) => {
    await page.goto('/welcome');
    await page.locator('.cta-btn').click();

    await page.locator('[data-test="generate-key-btn"]').click();

    const keyValue = page.locator('.key-value');
    await expect(keyValue).toBeVisible();
    await expect(keyValue).toHaveText(MOCK_ADMIN_KEY);
    await expect(page.locator('[data-test="continue-btn"]')).toBeVisible();
  });

  test('copy button flips to "Copied!" feedback', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    await page.goto('/welcome');
    await page.locator('.cta-btn').click();
    await page.locator('[data-test="generate-key-btn"]').click();

    await expect(page.locator('.key-value')).toBeVisible();
    const copyBtn = page.locator('.copy-btn');
    await copyBtn.click();
    await expect(copyBtn).toHaveClass(/copy-btn--copied/);
  });

  test('continue navigates to /settings#general', async ({ page }) => {
    await page.goto('/welcome');
    await page.locator('.cta-btn').click();
    await page.locator('[data-test="generate-key-btn"]').click();
    await expect(page.locator('.key-value')).toBeVisible();

    await page.locator('[data-test="continue-btn"]').click();

    await page.waitForURL(/\/settings#general$/);
    expect(page.url()).toContain('/settings#general');
  });

  test('failed setup surfaces an error with retry path', async ({ page }) => {
    // Override the per-test mock with a 500 once.
    let firstCall = true;
    await page.route('**/health/setup', (route) => {
      if (firstCall) {
        firstCall = false;
        return route.fulfill({ status: 500, json: { error: 'boom' } });
      }
      return route.fulfill({ json: { api_key: MOCK_ADMIN_KEY, role: 'admin' } });
    });

    await page.goto('/welcome');
    await page.locator('.cta-btn').click();
    await page.locator('[data-test="generate-key-btn"]').click();

    // Failed call → keygen-error block with localized 'Try again'
    await expect(page.locator('.keygen-error')).toBeVisible();

    // Retry button has the same data-test selector; click it.
    await page.locator('[data-test="generate-key-btn"]').click();
    await expect(page.locator('.key-value')).toHaveText(MOCK_ADMIN_KEY);
  });
});
