import { expect, test } from '@playwright/test';
import { resetDemo } from './reset-demo';

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

test('phone panel opens docked at 390px, reflows layout, maintains selection on close, prefills without sending, and highlights your report with jump', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('rd_tour_v2_off', '1'));
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('/coordinator/login');

  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
  await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible();

  // 1. Panel is closed by default
  const panel = page.getByTestId('citizen-phone-panel');
  await expect(panel).toHaveCount(0);

  const mainCol = page.locator('.coord-column');
  const initialColBox = await mainCol.boundingBox();
  expect(initialColBox).not.toBeNull();

  // 2. Click 'Try as a citizen' header button to open panel
  const tryCitizenBtn = page.getByTestId('try-citizen');
  await expect(tryCitizenBtn).toBeVisible();
  await tryCitizenBtn.click();

  await expect(panel).toBeVisible({ timeout: 10_000 });
  const panelBox = await panel.boundingBox();
  expect(panelBox).not.toBeNull();
  expect(panelBox!.width).toBeCloseTo(390, 1);

  // 3. Layout reflow: main column shrinks because panel is docked side-by-side (not overlaid)
  const reflowColBox = await mainCol.boundingBox();
  expect(reflowColBox).not.toBeNull();
  expect(reflowColBox!.width).toBeLessThan(initialColBox!.width - 200);

  // 4. Select a case in the queue, then close panel -> selection is maintained
  const firstCase = page.locator('.case-wrap').first();
  await firstCase.click();
  const selectedCaseId = await firstCase.getAttribute('data-case-id');

  const closePanelBtn = page.getByTestId('close-phone-panel');
  await closePanelBtn.click();
  await expect(panel).toHaveCount(0);

  // Selection is kept
  const stillSelected = page.locator('.case-wrap.sel');
  await expect(stillSelected).toBeVisible();
  expect(await stillSelected.getAttribute('data-case-id')).toBe(selectedCaseId);

  // 5. Reopen panel
  await tryCitizenBtn.click();
  await expect(panel).toBeVisible();

  const iframe = page.frameLocator('[data-testid="citizen-phone-frame"]');

  // 6. Example chips: clicking prefills textarea but does NOT auto-send
  const manglishChip = iframe.getByTestId('example-chip-manglish');
  await expect(manglishChip).toBeVisible({ timeout: 15_000 });
  await manglishChip.click();

  const textarea = iframe.locator('textarea');
  await expect(textarea).not.toBeEmpty();
  const textValue = await textarea.inputValue();
  expect(textValue).toContain('Kainakary');

  // Verify it was NOT auto-sent (still on report page, textarea still visible)
  await expect(textarea).toBeVisible();
  await expect(iframe.locator('.rid')).toHaveCount(0);

  // 7. Send the report from the panel
  const sendBtn = iframe.locator('.send-btn');
  await sendBtn.click();

  // Wait for review/card to appear and submit if multi-turn, or one-shot direct send
  const actionBtn = iframe.locator('.review-btn, .life-send, button:has-text("Review and send"), [data-testid="reporter-life-send"]').first();
  if (await actionBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await actionBtn.click();
    const sendNowBtn = iframe.getByRole('button', { name: 'Send now' });
    if (await sendNowBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await sendNowBtn.click();
    }
  }

  // Status page appears inside the phone iframe with RD-xxxx code
  const ridElement = iframe.locator('.rid');
  await expect(ridElement).toBeVisible({ timeout: 20_000 });
  const phonePublicCode = (await ridElement.innerText()).trim();
  expect(phonePublicCode).toMatch(/^RD-/);

  // 8. On the coordinator desk: 'Your report · RD-xxxx' chip appears without changing selection!
  const yourReportChip = page.getByTestId('your-report-chip');
  await expect(yourReportChip).toBeVisible({ timeout: 20_000 });
  await expect(yourReportChip).toContainText(phonePublicCode);

  // Current selection was NOT changed
  expect(await page.locator('.case-wrap.sel').getAttribute('data-case-id')).toBe(selectedCaseId);

  // 9. Clicking 'Your report' chip jumps to the newly landed case
  await yourReportChip.click();
  const newSelection = page.locator('.case-wrap.sel');
  await expect(newSelection).toBeVisible();
  const newSelectedId = await newSelection.getAttribute('data-case-id');
  expect(newSelectedId).not.toBe(selectedCaseId);
});

test('tour card and corner card never cover the phone panel', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);

  // 1. Tour corner card is visible
  const tourCorner = page.locator('.tour-corner-card');
  await expect(tourCorner).toBeVisible({ timeout: 10_000 });

  // 2. Open citizen phone panel
  const tryCitizenBtn = page.getByTestId('try-citizen');
  await tryCitizenBtn.click();
  const panel = page.getByTestId('citizen-phone-panel');
  await expect(panel).toBeVisible({ timeout: 10_000 });

  // 3. Tour corner card shifts to .with-panel and does not overlap panel
  await expect(tourCorner).toHaveClass(/with-panel/);
  const cornerBox = await tourCorner.boundingBox();
  const panelBox = await panel.boundingBox();
  expect(cornerBox).not.toBeNull();
  expect(panelBox).not.toBeNull();
  expect(cornerBox!.x + cornerBox!.width).toBeLessThanOrEqual(panelBox!.x);

  // 4. Start the tour and verify active tour callout also does not overlap panel
  const startBtn = page.getByTestId('tour-start');
  await startBtn.click();
  const tourCallout = page.getByTestId('tour');
  await expect(tourCallout).toBeVisible({ timeout: 5000 });
  const calloutBox = await tourCallout.boundingBox();
  expect(calloutBox).not.toBeNull();
  expect(calloutBox!.x + calloutBox!.width).toBeLessThanOrEqual(panelBox!.x);
});

