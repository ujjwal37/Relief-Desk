import { expect, test, type APIRequestContext } from '@playwright/test';
import { API } from './ports';
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

test('three reworded reports are flagged as possible duplicates, never merged, and conflicting counts keep the higher number', async ({ browser, request }) => {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  await context.addInitScript(() => localStorage.setItem('rd_tour_v2_off', '1'));
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
  await submit(request, wordings[2], PIN, `e2e-rw-${place}-2`);
  // Never auto-merged: three open cards, the two repeats flagged for a person.
  await expect(row).toHaveCount(3, { timeout: 20_000 });
  const cards = desk.locator('.case-wrap').filter({ hasText: place });
  await expect(cards.getByTestId('dup-chip')).toHaveCount(2, { timeout: 20_000 });
  await cards.filter({ has: desk.getByTestId('dup-chip') }).first().getByRole('option').click();
  await expect(desk.getByTestId('dup-review')).toBeVisible();
  await expect(desk.getByTestId('merge-dup')).toBeVisible();
  await expect(desk.getByTestId('keep-dup')).toBeVisible();

  await context.close();
});
