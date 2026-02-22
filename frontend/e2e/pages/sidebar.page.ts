/**
 * Page object for the Hive sidebar navigation.
 *
 * Encapsulates sidebar interactions including section expand/collapse,
 * submenu item clicks, and view transition waiting.
 *
 * Important: This SPA uses Vue's <Transition name="fade" mode="out-in">,
 * so we must wait for new content to be visible (not just attached) after
 * navigation. Never use networkidle, waitForNavigation, or waitForTimeout.
 */
import { type Locator, type Page, expect } from '@playwright/test';

export class SidebarPage {
  readonly page: Page;
  readonly sidebar: Locator;

  constructor(page: Page) {
    this.page = page;
    this.sidebar = page.locator('nav.sidebar');
  }

  /**
   * Expand a sidebar section by clicking its toggle if not already expanded.
   * Waits for the submenu to become visible.
   */
  async expandSection(sectionName: string) {
    const toggle = this.sidebar.locator('.nav-group-toggle', {
      hasText: sectionName,
    });

    // Find the sibling submenu (immediately after the toggle in DOM)
    const parent = this.sidebar.locator('.sidebar-nav');
    // The submenu div follows the toggle anchor. We locate it via the toggle's
    // nav-text content and then find the next .nav-submenu sibling.
    const submenu = toggle.locator('+ .nav-submenu');

    const isVisible = await submenu.isVisible().catch(() => false);
    if (!isVisible) {
      await toggle.click();
    }
    await expect(submenu).toBeVisible();
  }

  /**
   * Click a submenu item within a section. Expands the section first if needed.
   * After clicking, waits for the Vue fade transition to complete.
   */
  async clickSubmenuItem(sectionName: string, itemText: string) {
    await this.expandSection(sectionName);
    const toggle = this.sidebar.locator('.nav-group-toggle', {
      hasText: sectionName,
    });
    const submenu = toggle.locator('+ .nav-submenu');
    await submenu.locator('.submenu-item', { hasText: itemText }).click();
  }

  /**
   * Click a flat (non-expandable) sidebar link by its nav-text content.
   * Used for items like Triggers and Settings that don't have submenus
   * but are direct sidebar links.
   * Excludes .nav-group-toggle elements to avoid matching expandable sections.
   */
  async navigateToFlatLink(linkText: string) {
    const link = this.sidebar.locator(
      '.sidebar-nav > a:not(.nav-group-toggle)',
      {
        has: this.page.locator('.nav-text', { hasText: linkText }),
      },
    );
    await link.click();
  }

  /**
   * Wait for a view to render after navigation.
   * Checks for a heading (h1, h2, h3) or .page-title containing the given text.
   * Uses Playwright auto-retry to handle Vue Transition timing.
   */
  async waitForView(viewIdentifier: string) {
    await this.page
      .locator('h1, h2, h3, .page-title, .breadcrumb-current')
      .filter({ hasText: viewIdentifier })
      .first()
      .waitFor({ state: 'visible', timeout: 10000 });
  }
}
