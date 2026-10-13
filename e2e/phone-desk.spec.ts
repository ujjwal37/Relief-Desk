import { expect, test, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { resetDemo } from './reset-demo';

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

const SHOTS = '/opt/cursor/artifacts/screenshots';

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: false });
}

test('a phone report reaches the desk, merges, and comes back approved', async ({ browser }) => {
  fs.mkdirSync(SHOTS, { recursive: true });
  fs.mkdirSync('/opt/cursor/artifacts/videos', { recursive: true });
  const tag = `kfer${Date.now().toString(36).replace(/[0-9]/g, 'x')}`;
  const place = `Kainakary Ferry ${tag}`;
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    geolocation: { latitude: 9.416, longitude: 76.411 },
    permissions: ['geolocation'],
  });
  await context.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  const desk = await context.newPage();
  const phone = await context.newPage();
  await phone.setViewportSize({ width: 390, height: 844 });

  await desk.goto('/coordinator/login');
  await desk.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await desk.waitForURL(/\/coordinator\/command/);
  await expect(desk.getByRole('heading', { name: 'Cases' })).toBeVisible();
  await shot(desk, 'phone-desk-queue-before');

  await phone.goto('/report');
  await phone.getByRole('button', { name: 'Prefer a form?' }).click();
  await phone.locator('.quick-tiles button').first().click();
  await phone.locator('label.field input[type="text"]').fill(place);
  await phone.locator('label.field input[type="number"]').fill('4');
  await shot(phone, 'phone-desk-report-form');
  await phone.getByRole('button', { name: 'Send now' }).click();
  await phone.waitForURL(/\/status/);
  await expect(phone.getByText('Sent. A coordinator will review it.')).toBeVisible();
  const statusUrl = phone.url();
  await shot(phone, 'phone-desk-sent');

  const row = desk.getByRole('option', { name: new RegExp(tag) });
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.click();
  await shot(desk, 'phone-desk-arrived');

  await phone.goto('/report');
  await phone.getByRole('button', { name: 'Prefer a form?' }).click();
  await phone.locator('.quick-tiles button').first().click();
  await phone.locator('label.field input[type="text"]').fill(`Another report from ${place}, water still rising`);
  await phone.locator('label.field input[type="number"]').fill('4');
  await phone.getByRole('button', { name: 'Send now' }).click();
  await phone.waitForURL(/\/status/);

  const merged = desk.locator('.case-wrap').filter({ hasText: tag }).getByRole('button', { name: '2 reports', exact: true });
  await expect(merged).toBeVisible({ timeout: 20_000 });
  await shot(desk, 'phone-desk-merged');

  const approve = desk.getByRole('button', { name: 'Approve and send' });
  await expect(approve).toBeEnabled({ timeout: 20_000 });
  await shot(desk, 'phone-desk-suggest');
  await approve.click();
  await expect(desk.locator('.toast')).toContainText('Dispatch Approved');
  await shot(desk, 'phone-desk-approved');

  await phone.goto(statusUrl);
  await expect(phone.getByText('A team is on the way.')).toBeVisible({ timeout: 20_000 });
  await shot(phone, 'phone-desk-on-the-way');
  await context.close();
});
