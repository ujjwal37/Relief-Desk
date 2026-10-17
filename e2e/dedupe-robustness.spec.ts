import { expect, test, type APIRequestContext } from '@playwright/test';
import { API } from './ports';
import { openDedupeDetails, openHowItDecided, openTechnical } from './desk-ui';
import { resetDemo } from './reset-demo';

const PIN = { lat: 8.11, lng: 77.21 };

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

async function submit(request: APIRequestContext, text: string, pin: { lat: number; lng: number }, key: string) {
  const response = await request.post(`${API}/api/reports`, {
    data: {
      text,
      raw_text: text,
      lang: 'en',
      channel: 'text',
      location_pin: pin,
      idempotency_key: key,
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}

test('three reworded reports become one case, and conflicting counts keep the higher number', async ({ browser, request }) => {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  await context.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  const desk = await context.newPage();
  await desk.goto('/coordinator/login');
  await desk.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await desk.waitForURL(/\/coordinator\/command/);
  await expect(desk.getByRole('heading', { name: 'Cases' })).toBeVisible();

  const place = `Bramble${Date.now().toString(36).replace(/[0-9]/g, 'x')}`;
  const wordings = [
    `4 people stranded on the roof at ${place} jetty, send a boat`,
    `People stranded above the water at ${place} jetty, send a rescue boat`,
    `Still stranded at ${place} jetty, send a boat, people are on the roof`,
  ];
  await submit(request, wordings[0], PIN, `e2e-rw-${place}-0`);
  const row = desk.getByRole('option', { name: new RegExp(place) });
  await expect(row).toHaveCount(1, { timeout: 20_000 });
  await submit(request, wordings[1], PIN, `e2e-rw-${place}-1`);
  const merged = desk.locator('.case-wrap').filter({ hasText: place });
  await expect(merged.getByRole('button', { name: '2 reports', exact: true })).toBeVisible({ timeout: 20_000 });
  await submit(request, wordings[2], PIN, `e2e-rw-${place}-2`);
  await expect(row).toHaveCount(1, { timeout: 20_000 });
  await expect(merged.getByRole('button', { name: '3 reports', exact: true })).toBeVisible();
  await row.click();
  await merged.getByRole('button', { name: '3 reports', exact: true }).click();
  const quotes = desk.getByRole('dialog', { name: 'Reports merged into this case' });
  await expect(quotes).toBeVisible();
  await expect(quotes.locator('blockquote')).toHaveCount(3);
  await expect(quotes).toContainText('roof');
  await expect(quotes).toContainText(place);
  await desk.keyboard.press('Escape');
  await expect(quotes).toBeHidden();
  const firstTrace = await openHowItDecided(desk);
  await openTechnical(firstTrace);
  const firstDup = await openDedupeDetails(firstTrace);
  await expect(firstDup).toContainText('Match evidence');
  await desk.keyboard.press('Escape');

  await context.close();
});
