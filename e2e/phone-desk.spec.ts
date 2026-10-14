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
  const tag = `Demo ${Date.now().toString().slice(-6)}`;
  const place = `Kainakary Ferry Jetty (${tag})`;
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
  const strip = desk.getByTestId('just-reported');
  await expect(strip).toBeVisible();
  await expect(strip).toContainText(tag);
  await expect(strip.getByText('New', { exact: true }).first()).toBeVisible();
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
  await expect(desk.locator('.toast')).toContainText('Dispatch approved');
  await shot(desk, 'phone-desk-approved');

  await phone.goto(statusUrl);
  await expect(phone.getByText('A team is on the way.')).toBeVisible({ timeout: 20_000 });
  await shot(phone, 'phone-desk-on-the-way');
  await context.close();
});

test('a Hindi report uses Hindi labels, reaches the desk, and the status stays Hindi', async ({ browser }) => {
  const tag = `qx${Date.now().toString(36).replace(/[0-9]/g, 'a')}`;
  const hindi = `वार्ड 12 में 6 लोग फंसे हैं, एक बच्चा भी है, पानी बढ़ रहा है, नाव भेजो। ${tag}`;
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    geolocation: { latitude: 9.498, longitude: 76.339 },
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

  await phone.goto('/report');
  await expect(phone.locator('textarea')).toHaveAttribute('lang', 'en-IN');
  await phone.getByRole('button', { name: 'Settings' }).click();
  const sheet = phone.locator('.rd-sheet');
  await expect(sheet.getByRole('button', { name: 'English' })).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'Hindi' })).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'Hinglish' })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: 'Malayalam' })).toHaveCount(0);
  await sheet.getByTestId('lang-more').click();
  await expect(sheet.getByRole('button', { name: 'Hinglish' })).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'Malayalam' })).toBeVisible();
  await sheet.getByRole('button', { name: 'Hindi' }).click();
  await phone.keyboard.press('Escape');
  await expect(phone.locator('.rd-sheet')).toHaveCount(0);

  await expect(phone.getByPlaceholder('बताइए क्या हुआ')).toBeVisible();
  await expect(phone.getByRole('button', { name: 'बाढ़ या पानी बढ़ रहा है' })).toBeVisible();
  await expect(phone.locator('textarea')).toHaveAttribute('lang', 'hi-IN');
  await phone.getByRole('button', { name: 'बोलें' }).click();
  await expect(phone.locator('.voice')).toHaveAttribute('data-voice-locale', 'hi-IN');
  await phone.locator('.voice').getByRole('button', { name: 'बंद करें' }).click();

  await phone.getByRole('button', { name: 'फ़ॉर्म चाहिए?' }).click();
  await expect(phone.locator('label.field', { hasText: 'स्थान / लैंडमार्क' })).toBeVisible();
  await expect(phone.getByRole('button', { name: 'पानी में फंसे हैं' })).toBeVisible();
  await phone.goto('/report');
  await expect(phone.getByPlaceholder('बताइए क्या हुआ')).toBeVisible();

  await phone.locator('textarea').fill(hindi);
  await phone.getByRole('button', { name: 'भेजें', exact: true }).click();
  // "बचाव" also appears in the chat and in tips. Read it from the card's type chip only.
  await expect(phone.locator('rd-confirmation-card .type-chip')).toHaveText('बचाव', { timeout: 20_000 });
  await phone.getByRole('button', { name: 'अभी भेजें', exact: true }).click();
  await phone.waitForURL(/\/status/);
  await expect(phone.getByText('भेज दिया। एक संयोजक देखेगा।')).toBeVisible();
  await expect(phone.getByText('सबसे ऊँची सुरक्षित जगह पर जाएँ।')).toBeVisible();
  const statusUrl = phone.url();

  const row = desk.getByRole('option', { name: new RegExp(tag) });
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.scrollIntoViewIfNeeded();
  await expect(row).toContainText('6');
  await expect(row).toContainText(/Ward 12/);
  await row.click();
  await desk.getByRole('button', { name: 'More details' }).click();
  await desk.getByRole('button', { name: 'Show original' }).click();
  await expect(desk.locator('p.quote')).toContainText('6 लोग फंसे');
  await expect(desk.locator('p.quote')).toContainText(tag);

  const approve = desk.getByRole('button', { name: 'Approve and send' });
  await expect(approve).toBeEnabled({ timeout: 20_000 });
  await approve.click();
  await phone.goto(statusUrl);
  await expect(phone.getByText('टीम रास्ते में है।')).toBeVisible({ timeout: 20_000 });
  await context.close();
});
