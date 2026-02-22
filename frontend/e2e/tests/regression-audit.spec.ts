/**
 * Post-refactoring regression audit.
 * Tests all major pages and navigation flows against the live backend.
 * Run with: npx playwright test e2e/tests/regression-audit.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';

const BASE = 'http://localhost:3000';

// Helper: wait for sidebar to appear (app loaded)
async function waitForApp(page: Page) {
  await page.goto(BASE);
  await expect(page.locator('nav.sidebar')).toBeVisible({ timeout: 15000 });
}

// Helper: navigate via sidebar (each group is its own top-level toggle)
async function navigateViaSidebar(page: Page, group: string, item: string) {
  const toggle = page.locator('nav.sidebar .nav-group-toggle', { hasText: group });
  const submenu = toggle.locator('+ .nav-submenu');
  if (!(await submenu.isVisible())) {
    await toggle.click();
    await expect(submenu).toBeVisible();
  }
  await submenu.locator('.submenu-item', { hasText: item }).click();
  await page.waitForTimeout(500);
}

// ============================================================================
// 1. DASHBOARD
// ============================================================================
test.describe('Dashboard', () => {
  test('loads without errors', async ({ page }) => {
    await waitForApp(page);
    // Dashboard is the default view — uses h2 "Command Center"
    await expect(page.locator('text=Command Center')).toBeVisible({ timeout: 5000 });
  });
});

// ============================================================================
// 2. AI BACKENDS
// ============================================================================
test.describe('AI Backends', () => {
  test('All Backends page loads cards without double-refresh flicker', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'AI Backends', 'All Backends');

    await expect(page.locator('.backend-card').first()).toBeVisible({ timeout: 15000 });
    const cardCount = await page.locator('.backend-card').count();
    expect(cardCount).toBeGreaterThanOrEqual(1);
    await expect(page.locator('text=Loading backends')).not.toBeVisible();
  });

  test('Claude backend shows models after discovery', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'AI Backends', 'All Backends');
    await expect(page.locator('.backend-card').first()).toBeVisible({ timeout: 15000 });

    // Wait for model discovery
    await page.waitForTimeout(8000);

    const cards = page.locator('.backend-card');
    for (let i = 0; i < await cards.count(); i++) {
      const card = cards.nth(i);
      const name = await card.locator('h3').textContent();
      const models = await card.locator('.model-pill').count();
      console.log(`Backend "${name}": ${models} models`);
    }

    // Claude should now have models
    const claudeCard = page.locator('.backend-card', { hasText: 'Claude' });
    const claudeModels = await claudeCard.locator('.model-pill').count();
    expect(claudeModels).toBeGreaterThan(0);
  });

  test('clicking a backend card navigates to detail', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'AI Backends', 'All Backends');
    await expect(page.locator('.backend-card').first()).toBeVisible({ timeout: 15000 });

    await page.locator('.backend-card').first().click();
    await page.waitForTimeout(1500);

    await expect(page.locator('text=Accounts').first()).toBeVisible({ timeout: 5000 });
    expect(page.url()).toContain('/backends/');
  });

  test('deep link /backends/claude works', async ({ page }) => {
    await page.goto(`${BASE}/backends/claude`);
    await expect(page.locator('nav.sidebar')).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(2000);

    await expect(page.locator('text=Failed to load')).not.toBeVisible();
    await expect(page.locator('text=Accounts').first()).toBeVisible({ timeout: 5000 });
  });

  test('deep link /backends/codex works', async ({ page }) => {
    await page.goto(`${BASE}/backends/codex`);
    await expect(page.locator('nav.sidebar')).toBeVisible({ timeout: 15000 });
    await page.waitForTimeout(2000);

    await expect(page.locator('text=Failed to load')).not.toBeVisible();
    await expect(page.locator('text=Accounts').first()).toBeVisible({ timeout: 5000 });
  });

  test('Accounts page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'AI Backends', 'Accounts');
    await page.waitForTimeout(2000);

    const mainContent = await page.locator('.main-content, main, .content-area, .page-content').first().textContent();
    expect(mainContent).toBeTruthy();
  });
});

// ============================================================================
// 3. PLUGINS
// ============================================================================
test.describe('Plugins', () => {
  test('Plugins list page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Plugins', 'All Plugins');
    await page.waitForTimeout(2000);

    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });

  test('plugin detail loads on click', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Plugins', 'All Plugins');
    await page.waitForTimeout(2000);

    // Click first plugin in sidebar submenu (plugin names appear there)
    const pluginSubmenu = page.locator('nav.sidebar .nav-group-toggle', { hasText: 'Plugins' }).locator('+ .nav-submenu');
    const pluginItems = pluginSubmenu.locator('.submenu-item');
    const count = await pluginItems.count();
    console.log('Plugin submenu items:', count);

    // Find a plugin that has a name (not "All Plugins", "Design", "Explore", etc.)
    for (let i = 0; i < count; i++) {
      const text = await pluginItems.nth(i).textContent();
      if (text && !['All Plugins', 'Design a Plugin', 'Explore', 'Harness Integration'].includes(text.trim())) {
        console.log('Clicking plugin:', text?.trim());
        await pluginItems.nth(i).click();
        await page.waitForTimeout(2000);
        expect(page.url()).toContain('/plugins/');
        break;
      }
    }
  });
});

// ============================================================================
// 4-7. SKILLS, HOOKS, COMMANDS, RULES
// ============================================================================
test.describe('Skills', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Skills', 'Skill Library');
    await page.waitForTimeout(2000);
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });
});

test.describe('Hooks', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Hooks', 'All Hooks');
    await page.waitForTimeout(2000);
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });
});

test.describe('Commands', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Commands', 'All Commands');
    await page.waitForTimeout(2000);
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });
});

test.describe('Rules', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Rules', 'All Rules');
    await page.waitForTimeout(2000);
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });
});

// ============================================================================
// 8. TRIGGERS
// ============================================================================
test.describe('Triggers', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Triggers', 'Security Scan');
    await page.waitForTimeout(2000);
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });
});

// ============================================================================
// 9-12. ORGANIZATION ENTITIES
// ============================================================================
test.describe('Agents', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Agents', 'All Agents');
    await page.waitForTimeout(2000);
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });
});

test.describe('Teams', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Teams', 'All Teams');
    await page.waitForTimeout(2000);
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });
});

test.describe('Projects', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Projects', 'All Projects');
    await page.waitForTimeout(2000);
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });
});

test.describe('Products', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Products', 'All Products');
    await page.waitForTimeout(2000);
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });
});

// ============================================================================
// 13. TOKEN USAGE
// ============================================================================
test.describe('Token Usage', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    await navigateViaSidebar(page, 'Usage', 'Token Usage');
    await page.waitForTimeout(2000);
    await expect(page.locator('text=Failed to load')).not.toBeVisible();
  });
});

// ============================================================================
// 14. SETTINGS
// ============================================================================
test.describe('Settings', () => {
  test('page loads', async ({ page }) => {
    await waitForApp(page);
    const settingsLink = page.locator('nav.sidebar').locator('text=Settings');
    if (await settingsLink.isVisible()) {
      await settingsLink.click();
      await page.waitForTimeout(2000);
      const h1 = await page.locator('h1').first().textContent();
      console.log('Settings H1:', h1);
    }
  });
});

// ============================================================================
// 15. NAVIGATION — exhaustive sidebar crawl
// ============================================================================
test.describe('Navigation Consistency', () => {
  test('all sidebar items navigate without errors', async ({ page }) => {
    await waitForApp(page);

    const groups = page.locator('nav.sidebar .nav-group-toggle');
    const groupCount = await groups.count();
    const errors: string[] = [];

    for (let g = 0; g < groupCount; g++) {
      const groupText = (await groups.nth(g).textContent())?.trim();
      console.log(`\n--- Group: ${groupText} ---`);

      await groups.nth(g).click();
      await page.waitForTimeout(300);

      const submenu = groups.nth(g).locator('+ .nav-submenu');
      if (await submenu.isVisible()) {
        const items = submenu.locator('.submenu-item');
        const itemCount = await items.count();

        for (let i = 0; i < itemCount; i++) {
          const itemText = (await items.nth(i).textContent())?.trim();
          await items.nth(i).click();
          await page.waitForTimeout(800);

          const hasError = await page.locator('.error-state, text=Failed to load').first().isVisible().catch(() => false);
          const status = hasError ? 'ERROR' : 'OK';
          console.log(`  ${status}: ${itemText} -> ${page.url()}`);
          if (hasError) errors.push(`${groupText} > ${itemText}`);
        }
      }
    }

    if (errors.length > 0) {
      console.log('\nPages with errors:', errors);
    }
    expect(errors).toHaveLength(0);
  });

  test('browser back/forward works', async ({ page }) => {
    await waitForApp(page);

    await navigateViaSidebar(page, 'AI Backends', 'All Backends');
    await page.waitForTimeout(1000);
    const url1 = page.url();

    await navigateViaSidebar(page, 'Teams', 'All Teams');
    await page.waitForTimeout(1000);
    const url2 = page.url();

    await navigateViaSidebar(page, 'Projects', 'All Projects');
    await page.waitForTimeout(1000);

    await page.goBack();
    await page.waitForTimeout(1000);
    expect(page.url()).toBe(url2);

    await page.goBack();
    await page.waitForTimeout(1000);
    expect(page.url()).toBe(url1);

    await page.goForward();
    await page.waitForTimeout(1000);
    expect(page.url()).toBe(url2);
  });
});

// ============================================================================
// 16. RAPID NAVIGATION — no blank pages
// ============================================================================
test.describe('Rapid Navigation Stability', () => {
  test('rapid page switches do not produce blank content', async ({ page }) => {
    // Capture console errors
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await waitForApp(page);

    const pages = [
      { group: 'AI Backends', item: 'All Backends' },
      { group: 'Hooks', item: 'All Hooks' },
      { group: 'Commands', item: 'All Commands' },
      { group: 'Rules', item: 'All Rules' },
      { group: 'Skills', item: 'Skill Library' },
      { group: 'Teams', item: 'All Teams' },
      { group: 'Agents', item: 'All Agents' },
      { group: 'Projects', item: 'All Projects' },
      { group: 'Products', item: 'All Products' },
      { group: 'Plugins', item: 'All Plugins' },
    ];

    // Navigate through pages rapidly — 3 full cycles
    for (let cycle = 0; cycle < 3; cycle++) {
      for (const p of pages) {
        await navigateViaSidebar(page, p.group, p.item);
        await page.waitForTimeout(200);
      }
    }

    // After rapid navigation, the last page should have content
    await page.waitForTimeout(2000);

    const url = page.url();
    const dataView = await page.locator('.content-wrapper').getAttribute('data-view');
    console.log('Final URL:', url);
    console.log('data-view attribute:', dataView);

    // Check the page has visible content (not blank)
    const mainContent = page.locator('.main-content, main');
    await expect(mainContent).toBeVisible();

    // Check for visible content in the main area — heading, card, or loading spinner
    const contentWrapper = page.locator('.content-wrapper');
    const wrapperChildCount = await contentWrapper.evaluate(el => el.children.length);
    console.log('Content wrapper child count:', wrapperChildCount);

    const hasContent = await page.locator('.main-content h1, .main-content .page-header, .main-content .loading-state, .main-content .empty-state, .main-content .page-layout').first().isVisible().catch(() => false);
    console.log('Has visible content:', hasContent);

    if (!hasContent) {
      const html = await contentWrapper.innerHTML();
      console.log('Content wrapper HTML (first 500 chars):', html.substring(0, 500));
      console.log('Has sidebar:', await page.locator('nav.sidebar').isVisible());
      // Check for error boundary message
      const errorAttr = await contentWrapper.locator('[data-error]').getAttribute('data-error').catch(() => null);
      console.log('Render error:', errorAttr);
      console.log('Console errors:', consoleErrors.filter(e => e.includes('AppViewManager')));
    }

    expect(wrapperChildCount).toBeGreaterThan(0);
    expect(hasContent).toBeTruthy();
  });
});

// ============================================================================
// 17. API HEALTH
// ============================================================================
test.describe('API Health', () => {
  test('critical endpoints return 200', async ({ page }) => {
    await page.goto(BASE);

    const endpoints = [
      '/admin/backends',
      '/admin/triggers',
      '/admin/plugins',
      '/admin/agents',
      '/admin/teams',
      '/admin/projects',
      '/admin/products',
      '/admin/hooks',
      '/admin/commands',
      '/admin/rules',
    ];

    for (const endpoint of endpoints) {
      const result = await page.evaluate(async (url) => {
        try {
          const res = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
          return { status: res.status, ok: res.ok };
        } catch (e: any) {
          return { status: 0, error: e.message };
        }
      }, `${BASE}${endpoint}`);

      console.log(`${endpoint}: ${result.status} ${result.ok ? '✓' : '✗'}`);
      expect(result.status).toBe(200);
    }
  });
});
