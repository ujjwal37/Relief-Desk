import { expect, test } from '@playwright/test';
import { resetDemo } from './reset-demo';

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

test('a phone report updates the desk, and an approval updates the phone, with no reload', async ({ browser }) => {
  const tag = `Demo ${Date.now().toString().slice(-6)}`;
  const place = `Kainakary Ferry Jetty (${tag})`;
  const deskContext = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const phoneContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    geolocation: { latitude: 9.416, longitude: 76.411 },
    permissions: ['geolocation'],
  });
  await deskContext.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  await phoneContext.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  const desk = await deskContext.newPage();
  const phone = await phoneContext.newPage();

  const live = desk.waitForResponse((res) => res.url().includes('/api/events') && res.ok(), { timeout: 20_000 });
  await desk.goto('/coordinator/login');
  await desk.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await desk.waitForURL(/\/coordinator\/command/);
  await live;

  await phone.goto('/report');
  await phone.getByRole('button', { name: 'Prefer a form?' }).click();
  await phone.locator('.quick-tiles button').first().click();
  await phone.locator('label.field input[type="text"]').fill(place);
  await phone.locator('label.field input[type="number"]').fill('4');
  await phone.getByRole('button', { name: 'Send now' }).click();
  await phone.waitForURL(/\/status/);
  await expect(phone.getByText('Sent. A coordinator will review it.')).toBeVisible();

  const row = desk.getByRole('option', { name: new RegExp(tag) });
  await expect(row).toBeVisible({ timeout: 3_000 });
  await row.click();
  const approve = desk.getByRole('button', { name: 'Approve and send' });
  await expect(approve).toBeEnabled({ timeout: 20_000 });
  await approve.click();

  await expect(phone.getByText('A team is on the way.')).toBeVisible({ timeout: 3_000 });
  await deskContext.close();
  await phoneContext.close();
});
