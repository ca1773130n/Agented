/**
 * Integration tests for trigger execution flow — live backend, NO API mocking.
 *
 * These tests verify the full-stack data flow from backend to frontend.
 * The specific endpoint GET /admin/triggers/bot-pr-review/executions
 * previously returned 500 in production while all unit tests passed.
 * This test suite ensures that never happens again.
 */
import { test, expect } from '../../fixtures/live-backend';

test.describe('Trigger Execution Flow (live backend)', () => {
  test.describe.configure({ mode: 'serial' });

  test.beforeAll(async ({ request }) => {
    // Verify backend is ready before running any tests.
    // Uses Playwright's global APIRequestContext (not page.request).
    const response = await request.get('/health/readiness');
    expect(response.status()).toBe(200);
  });

  test('navigates to app and sees sidebar', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav.sidebar')).toBeVisible();
  });

  test('trigger execution history endpoint returns valid data', async ({ page }) => {
    // Directly verify the API endpoint that previously returned 500
    const response = await page.request.get('/admin/triggers/bot-pr-review/executions');
    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data).toHaveProperty('executions');
    expect(data).toHaveProperty('total');
    expect(Array.isArray(data.executions)).toBeTruthy();
    expect(typeof data.total).toBe('number');
  });

  test('trigger execution history for security trigger returns valid data', async ({ page }) => {
    const response = await page.request.get('/admin/triggers/bot-security/executions');
    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data).toHaveProperty('executions');
    expect(data).toHaveProperty('total');
    expect(Array.isArray(data.executions)).toBeTruthy();
    expect(typeof data.total).toBe('number');
  });

  test('trigger list endpoint returns predefined triggers', async ({ page }) => {
    const response = await page.request.get('/admin/triggers');
    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data).toHaveProperty('triggers');
    expect(Array.isArray(data.triggers)).toBeTruthy();
    expect(data.triggers.length).toBeGreaterThanOrEqual(2);

    for (const trigger of data.triggers) {
      expect(trigger).toHaveProperty('id');
      expect(trigger).toHaveProperty('name');
      expect(trigger).toHaveProperty('backend_type');
    }
  });

  test('health check endpoint is responsive', async ({ page }) => {
    const response = await page.request.get('/health/readiness');
    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data).toHaveProperty('status');
  });
});
