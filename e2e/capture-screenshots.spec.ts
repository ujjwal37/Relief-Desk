import { expect, test } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { resetDemo } from './reset-demo';

const ARTIFACT_DIR = 'C:/Users/aggar/.gemini/antigravity/brain/3e0ebfa0-87f4-4a84-a7a2-814a0a7a9c86';
const SHOTS_DIRS = [
  path.join(process.cwd(), 'e2e', 'screenshots'),
  ARTIFACT_DIR,
];

for (const dir of SHOTS_DIRS) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

async function shot(page: any, filename: string): Promise<void> {
  for (const dir of SHOTS_DIRS) {
    await page.screenshot({ path: path.join(dir, filename) });
  }
}

async function noHorizontalOverflow(page: any): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test('capture required screenshots at 1440x900', async ({ page, request }) => {
  await resetDemo(request);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));

  // 1. Home idle (English, Dark)
  await page.goto('/coordinator/login');
  await expect(page.getByRole('button', { name: 'Enter as demo coordinator' })).toBeVisible();
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
  await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible();

  // Explicitly ensure Dark mode
  const moreBtn = page.locator('.more-btn');
  await moreBtn.click();
  await page.getByRole('button', { name: 'Dark', exact: true }).click();
  await page.locator('.menu-back').click({ position: { x: 4, y: 4 } });
  await noHorizontalOverflow(page);
  await shot(page, 'home-idle-dark-en.png');

  // 2. Home idle (English, Light)
  await moreBtn.click();
  await page.getByRole('button', { name: 'Light', exact: true }).click();
  await page.locator('.menu-back').click({ position: { x: 4, y: 4 } });
  await noHorizontalOverflow(page);
  await shot(page, 'home-idle-light-en.png');

  // Switch back to Dark for remaining screenshots
  await moreBtn.click();
  await page.getByRole('button', { name: 'Dark', exact: true }).click();
  await page.locator('.menu-back').click({ position: { x: 4, y: 4 } });

  // 3. Home idle (Hindi, Dark)
  await moreBtn.click();
  await page.getByRole('button', { name: 'Hindi', exact: true }).click();
  await page.locator('.menu-back').click({ position: { x: 4, y: 4 } });
  await noHorizontalOverflow(page);
  await shot(page, 'home-idle-dark-hi.png');

  // Switch back to English
  await moreBtn.click();
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await page.locator('.menu-back').click({ position: { x: 4, y: 4 } });

  // Select Hindi case INC-001 so it has proposals and matches
  const hindiCase = page.getByRole('option', { name: /3 children and 2/ });
  await hindiCase.scrollIntoViewIfNeeded();
  await hindiCase.click();

  // 4. Why this team modal
  const whyBtn = page.getByRole('button', { name: /More details/i }).first();
  await expect(whyBtn).toBeVisible();
  await whyBtn.click();
  const whyModal = page.locator('[data-testid="why-team-popup"]');
  await expect(whyModal).toBeVisible();
  await shot(page, 'why-this-team-modal.png');
  await whyModal.locator('.close-btn').click();
  await expect(whyModal).toBeHidden();

  // 5. Step Details popup
  const firstStep = page.locator('[data-testid="stepper-node-intake"]');
  await expect(firstStep).toBeVisible();
  await firstStep.click();
  const stepPopup = page.locator('[data-testid="step-details"]');
  await expect(stepPopup).toBeVisible();
  await shot(page, 'step-details-popup.png');
  await stepPopup.locator('.close-btn').click();
  await expect(stepPopup).toBeHidden();

  // 6. Teams page
  await page.locator('nav.tabs a').filter({ hasText: 'Teams' }).click();
  await page.waitForURL(/\/coordinator\/teams/);
  await expect(page.getByRole('heading', { name: 'Teams' })).toBeVisible();
  await expect(page.locator('li.card').first()).toBeVisible();
  await noHorizontalOverflow(page);
  await shot(page, 'teams-page.png');

  // 7. Home while a sample is processing
  await page.locator('nav.tabs a').first().click();
  await page.waitForURL(/\/coordinator\/command/);
  const hindiSampleBtn = page.getByTestId('sample-hindi');
  await hindiSampleBtn.click();
  await page.waitForTimeout(400);
  await shot(page, 'home-sample-processing.png');
});
