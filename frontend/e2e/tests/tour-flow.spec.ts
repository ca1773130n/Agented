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

  // OB-47: tour state persists across page reload — the user can
  // navigate away (or accidentally reload) and pick up where they
  // left off without losing progress.
  test('persists across reload', async ({ tourPage, page }) => {
    await tourPage.startTour();
    await tourPage.expectStepText('STEP 2 OF 8');

    // Advance two steps so the persisted state is non-trivial.
    await tourPage.clickNext();
    await tourPage.expectStepText('STEP 3 OF 8');

    await page.reload();
    await tourPage.expectVisible();
    await tourPage.expectStepText('STEP 3 OF 8');
  });

  // OB-36 + OB-47: prefers-reduced-motion disables tour animations.
  // The CSS @media block lives in TourSpotlight.vue; this verifies
  // it actually reaches the rendered element.
  test('reduced motion disables spotlight glow animation', async ({ tourPage, page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await tourPage.startTour();
    await tourPage.expectVisible();

    // Some pages may not paint the glow until the spotlight has a
    // resolved target rect; wait for it.
    const glow = page.locator('.tour-spotlight-glow').first();
    await glow.waitFor({ state: 'attached' });
    const animationName = await glow.evaluate(
      (el) => getComputedStyle(el).animationName,
    );
    expect(animationName).toBe('none');
  });

  // OB-37 + OB-47: focus is trapped within the tooltip + the
  // highlighted target. The strictest unit-level check would assert
  // focus stays inside `.tour-overlay`, but the criterion explicitly
  // includes the target element — which lives in the page, not the
  // overlay. Instead we assert the negation: focus must NEVER land
  // on the global chrome (header/nav/aside) while a tour is active.
  test('focus stays out of header/sidebar while tour is active', async ({ tourPage, page }) => {
    await tourPage.startTour();
    await tourPage.expectVisible();

    for (let i = 0; i < 6; i++) {
      await page.keyboard.press('Tab');
    }
    const inChrome = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el) return false;
      return el.closest('header, nav, aside') !== null;
    });
    expect(inChrome).toBe(false);
  });

  // OB-44 + OB-47: a modal that opens during a tour step (the
  // AccountWizard during the backends step) is still interactive,
  // and the tour overlay reduces its dimming so the modal isn't
  // visually fighting the spotlight.
  //
  // Strategy: the unit-level test in TourOverlay.test.ts already
  // covers prop flow (`isModalOpen` → `.modal-open` + spotlight
  // `:reduced`). E2E adds the integration: the click on the
  // highlighted Add Account button actually mounts the wizard and
  // the wizard receives focus / pointer events.
  test('modal opens and is interactive during backends step', async ({ tourPage, page }) => {
    await tourPage.startTour();
    await tourPage.expectVisible();

    // Advance past Workspace (step 2) to backends.claude (step 3).
    await tourPage.clickNext();
    await tourPage.expectStepText('STEP 3 OF 8');

    // The spotlight target on this step is `[data-tour="add-account-btn"]`.
    const addAccountBtn = page.locator('[data-tour="add-account-btn"]').first();
    await expect(addAccountBtn).toBeVisible();
    await addAccountBtn.click();

    // AccountWizard mounts with a stable `data-tour="account-wizard"`
    // anchor on its container.
    const wizard = page.locator('[data-tour="account-wizard"]');
    await expect(wizard).toBeVisible();

    // The wizard's close button must be clickable — i.e., the tour
    // overlay isn't intercepting pointer events. We don't actually
    // close it (some tour state machines auto-cancel on close); we
    // just verify hover-ability and pointer-events.
    const wizardClose = wizard.locator('.wizard-close');
    await expect(wizardClose).toBeVisible();
    const pointerEvents = await wizardClose.evaluate(
      (el) => getComputedStyle(el).pointerEvents,
    );
    expect(pointerEvents).not.toBe('none');

    // App.vue's `provide('setTourModalOpen', ...)` should have flipped
    // — verify TourSpotlight entered reduced mode by reading its
    // `tour-spotlight--reduced` class. Either that OR the dim
    // fallback's `.modal-open` class (when no spotlight target) is
    // acceptable evidence that `modalOpenDuringTour` propagated.
    const overlayInModalMode = await page.evaluate(() => {
      const reducedSpot = document.querySelector('.tour-spotlight--reduced');
      const modalOpenDim = document.querySelector('.tour-dim-fallback.modal-open');
      return Boolean(reducedSpot) || Boolean(modalOpenDim);
    });
    expect(overlayInModalMode).toBe(true);
  });
});
