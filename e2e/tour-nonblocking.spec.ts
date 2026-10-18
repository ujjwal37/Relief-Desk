import { expect, test } from '@playwright/test';
import { resetDemo } from './reset-demo';

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

test('non-blocking tour card appears after login, allows typing, skip persists, and header tour replays', async ({ page }) => {
  // Ensure tour flags are clean so corner card triggers after demo login
  await page.addInitScript(() => {
    localStorage.removeItem('rd_tour_v2_off');
    sessionStorage.clear();
  });

  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('/coordinator/login');

  // 1. Enter as demo coordinator -> corner card appears
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);

  const cornerCard = page.getByTestId('tour-corner-card');
  await expect(cornerCard).toBeVisible({ timeout: 10_000 });
  await expect(cornerCard).toContainText('Take a 60-second tour');

  // 2. Typing works while it shows (non-blocking: no modal, no backdrop scrim, no focus trap)
  const searchInput = page.locator('#coord-search');
  await expect(searchInput).toBeVisible();
  await searchInput.fill('Kainakary');
  await expect(searchInput).toHaveValue('Kainakary');
  await expect(cornerCard).toBeVisible();

  // 3. Skip persists across reload
  const skipBtn = cornerCard.getByTestId('tour-skip');
  await skipBtn.click();
  await expect(cornerCard).toBeHidden();

  const offFlag = await page.evaluate(() => localStorage.getItem('rd_tour_v2_off'));
  expect(offFlag).toBe('1');

  // Reload and verify corner card never auto-shows again
  await page.reload();
  await page.waitForURL(/\/coordinator\/command/);
  await page.waitForTimeout(1000);
  await expect(page.getByTestId('tour-corner-card')).toHaveCount(0);

  // 4. Header Tour replays
  const headerTour = page.getByTestId('header-tour');
  await expect(headerTour).toBeVisible();
  await headerTour.click();

  // Step 1: Life threats first
  const callout = page.getByTestId('tour');
  await expect(callout).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId('tour-outline')).toBeVisible();
  await expect(callout).toContainText(/Life threats first/i);

  // Advance to next step
  const nextBtn = callout.getByTestId('tour-next');
  await nextBtn.click();

  // Step 2: Step-by-step trace
  await expect(callout).toContainText(/trace/i);

  // Skip or close dismisses tour
  await callout.getByTestId('tour-skip').click();
  await expect(callout).toBeHidden();
});
