/**
 * E2E tests for the onboarding tour flow.
 *
 * Validates:
 * - Complete tour navigation via Next buttons (resolves Phase 4 deferred validation)
 * - Skip-all flow via Skip buttons
 * - Keyboard navigation (Tab/Enter/Space/Escape) (resolves Phase 6 deferred validation)
 *
 * The tour has 7 steps (displayed as STEP 2-8 because step 1 is the welcome page):
 *   workspace (2) -> backends.claude (3) -> backends.codex (4) -> backends.gemini (5)
 *   -> backends.opencode (6) -> monitoring (7) -> harness (8) -> product -> project -> teams
 *
 * Note: displayStepNumber = stepIndex + 2 (step 1 is the WelcomePage, not managed by useTour).
 * totalSteps = 8 (STEPS.length + 1 for welcome).
 */
import { test, expect } from '../fixtures/tour';

test.describe('Tour flow — complete navigation', () => {
  test('completes full tour with Next clicks', async ({ tourPage }) => {
    await tourPage.startTour();

    // Step 1 (displayed as STEP 2 OF 8): Workspace
    await tourPage.expectVisible();
    await tourPage.expectStepText('STEP 2 OF 8');

    // Click Next through workspace -> backends.claude (STEP 3)
    await tourPage.clickNext();
    await tourPage.expectStepText('STEP 3 OF 8');

    // backends.claude -> backends.codex (still STEP 3 — substeps share step number)
    // The displayStepNumber stays at 3 while in backends substeps because
    // it's currentStepIndex (1) + 2 = 3 for the entire backends step.
    await tourPage.clickNext();
    // Still step 3 (backends substep 2: codex)
    await tourPage.expectStepText('STEP 3 OF 8');

    // backends.codex -> backends.gemini
    await tourPage.clickNext();
    await tourPage.expectStepText('STEP 3 OF 8');

    // backends.gemini -> backends.opencode
    await tourPage.clickNext();
    await tourPage.expectStepText('STEP 3 OF 8');

    // backends.opencode -> monitoring (next parent step, STEP 4)
    await tourPage.clickNext();
    await tourPage.expectStepText('STEP 4 OF 8');

    // monitoring -> harness (STEP 5)
    await tourPage.clickNext();
    await tourPage.expectStepText('STEP 5 OF 8');

    // harness -> product (STEP 6)
    await tourPage.clickNext();
    await tourPage.expectStepText('STEP 6 OF 8');

    // product -> project (STEP 7)
    await tourPage.clickNext();
    await tourPage.expectStepText('STEP 7 OF 8');

    // project -> teams (STEP 8)
    await tourPage.clickNext();
    await tourPage.expectStepText('STEP 8 OF 8');

    // teams -> complete (tour ends)
    await tourPage.clickNext();
    await tourPage.expectHidden();
  });

  test('completes tour using Skip buttons on skippable steps', async ({ tourPage }) => {
    await tourPage.startTour();
    await tourPage.expectVisible();

    // Workspace (STEP 2) — not skippable, must click Next
    await tourPage.expectStepText('STEP 2 OF 8');
    await tourPage.clickNext();

    // Backends (STEP 3) — skippable, skip the entire step
    await tourPage.expectStepText('STEP 3 OF 8');
    await tourPage.clickSkip();

    // Monitoring (STEP 4) — not skippable, must click Next
    await tourPage.expectStepText('STEP 4 OF 8');
    await tourPage.clickNext();

    // Harness (STEP 5) — not skippable, must click Next
    await tourPage.expectStepText('STEP 5 OF 8');
    await tourPage.clickNext();

    // Product (STEP 6) — skippable
    await tourPage.expectStepText('STEP 6 OF 8');
    await tourPage.clickSkip();

    // Project (STEP 7) — skippable
    await tourPage.expectStepText('STEP 7 OF 8');
    await tourPage.clickSkip();

    // Teams (STEP 8) — skippable
    await tourPage.expectStepText('STEP 8 OF 8');
    await tourPage.clickSkip();

    // Tour should be complete
    await tourPage.expectHidden();
  });

  test('keyboard navigation through tour', async ({ tourPage, page }) => {
    await tourPage.startTour();
    await tourPage.expectVisible();

    // Verify initial step
    await tourPage.expectStepText('STEP 2 OF 8');

    // Tab to the Next button and press Enter to advance
    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');

    // Should advance to step 3 (backends)
    await tourPage.expectVisible();
    await tourPage.expectStepText('STEP 3 OF 8');

    // Tab to Skip button (first focusable) and press Space to skip
    // Backends step is skippable so Skip button should be present
    await expect(tourPage.skipBtn).toBeVisible();
    await page.keyboard.press('Tab');
    await page.keyboard.press('Space');

    // Should advance to step 4 (monitoring)
    await tourPage.expectStepText('STEP 4 OF 8');

    // Verify Escape key does NOT dismiss the tour
    await page.keyboard.press('Escape');
    await tourPage.expectVisible();
    await tourPage.expectStepText('STEP 4 OF 8');

    // Continue with keyboard — Tab to Next, Enter to advance
    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');
    await tourPage.expectStepText('STEP 5 OF 8');
  });
});
