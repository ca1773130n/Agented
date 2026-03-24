/**
 * Tour-specific Playwright fixture extending the base Agented fixture.
 *
 * Adds API mocks for tour-related endpoints and provides a TourPage
 * helper class with methods for navigating the onboarding tour.
 *
 * The tour is triggered via the `?tour=start` query parameter.
 * Tour state persists in localStorage under 'agented-tour-state'.
 */
import { type Locator, type Page } from '@playwright/test';
import { test as base, expect } from './base';

// ---------------------------------------------------------------------------
// Mock responses for tour-specific endpoints
// ---------------------------------------------------------------------------

const MOCK_INSTANCE_ID = { instance_id: 'e2e-test-uuid' };

const MOCK_AUTH_STATUS = {
  needs_setup: false,
  auth_required: false,
  authenticated: true,
};

const MOCK_SETTINGS = {
  settings: { workspace_dir: '' },
};

const MOCK_BACKEND_DETAIL = {
  id: 'backend-claude',
  name: 'Claude',
  type: 'claude',
  installed: true,
  accounts: [],
  models: ['opus-4', 'sonnet-4'],
};

// ---------------------------------------------------------------------------
// TourPage helper
// ---------------------------------------------------------------------------

class TourPage {
  readonly page: Page;
  readonly overlay: Locator;
  readonly nextBtn: Locator;
  readonly skipBtn: Locator;
  readonly stepCounter: Locator;
  readonly bottomBar: Locator;
  readonly stepMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.overlay = page.locator('.tour-overlay');
    this.nextBtn = page.locator('.tour-next-btn');
    this.skipBtn = page.locator('.tour-skip-btn');
    this.stepCounter = page.locator('.tour-step-counter');
    this.bottomBar = page.locator('.tour-bottom-bar');
    this.stepMessage = page.locator('.tour-step-message');
  }

  /** Click the Next button and wait for the overlay to settle. */
  async clickNext() {
    await this.nextBtn.click();
    // Wait for overlay to remain visible (transition settles)
    await expect(this.bottomBar).toBeVisible();
  }

  /** Click the Skip button and wait for the overlay to settle. */
  async clickSkip() {
    await expect(this.skipBtn).toBeVisible();
    await this.skipBtn.click();
  }

  /** Assert the tour overlay is visible. */
  async expectVisible() {
    await expect(this.overlay).toBeVisible();
  }

  /** Assert the tour overlay is not visible / detached. */
  async expectHidden() {
    await expect(this.overlay).not.toBeVisible();
  }

  /** Assert the step counter contains the given text (e.g., "STEP 2 OF 8"). */
  async expectStepText(text: string) {
    await expect(this.stepCounter).toContainText(text);
  }

  /**
   * Navigate to the app with ?tour=start and wait for the tour overlay.
   * The overlay appears after auth check + sidebar data load.
   */
  async startTour() {
    await this.page.goto('/?tour=start');
    // The tour starts by navigating to the first step route (/settings).
    // Wait for the overlay bottom bar to be visible.
    await expect(this.bottomBar).toBeVisible({ timeout: 10000 });
  }
}

// ---------------------------------------------------------------------------
// Extended fixture
// ---------------------------------------------------------------------------

type TourFixtures = {
  tourPage: TourPage;
};

export const test = base.extend<TourFixtures>({
  page: async ({ page }, use) => {
    // Add tour-specific API mocks ON TOP of the base fixture mocks.
    await page.route('**/health/instance-id', (route) =>
      route.fulfill({ json: MOCK_INSTANCE_ID }),
    );
    await page.route('**/health/auth-status', (route) =>
      route.fulfill({ json: MOCK_AUTH_STATUS }),
    );
    await page.route('**/api/settings', (route) =>
      route.fulfill({ json: MOCK_SETTINGS }),
    );
    // Catch-all for individual backend detail requests
    await page.route('**/admin/backends/*', (route) =>
      route.fulfill({ json: MOCK_BACKEND_DETAIL }),
    );
    // Mock setup/bundle-install to prevent side effects
    await page.route('**/api/setup/bundle-install', (route) =>
      route.fulfill({ json: { status: 'already_installed' } }),
    );

    // Clear tour localStorage before each test for isolation
    await page.addInitScript(() => {
      localStorage.removeItem('agented-tour-state');
    });

    await use(page);
  },

  tourPage: async ({ page }, use) => {
    await use(new TourPage(page));
  },
});

export { expect };
