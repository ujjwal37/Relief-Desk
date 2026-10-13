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
  await expect(desk.getByTestId('report-quote')).toHaveCount(3);
  await expect(desk.getByTestId('report-quote').nth(0)).toContainText('roof');
  await expect(desk.getByTestId('report-quote').nth(1)).toContainText(place);
  await desk.locator('.detail').getByRole('button', { name: 'How it decided' }).click();
  await expect(desk.getByRole('dialog')).toContainText('Similarity');
  await desk.keyboard.press('Escape');

  const ranges = `Oakbend${Date.now().toString(36).replace(/[0-9]/g, 'y')}`;
  await submit(request, `At ${ranges} ghat, 2-3 people on the roof need a boat, send a rescue boat`, PIN, `e2e-rg-${ranges}-a`);
  await submit(request, `${ranges} ghat: 4-5 people stranded, send a rescue boat`, PIN, `e2e-rg-${ranges}-b`);
  const conflict = desk.getByRole('option', { name: new RegExp(ranges) });
  await expect(conflict).toHaveCount(1, { timeout: 20_000 });
  await expect(conflict).toContainText('Counts differ: 2-3 vs 4-5');
  await expect(conflict).toContainText('5');
  await conflict.click();
  await expect(desk.locator('.detail').getByTestId('counts-differ')).toContainText('Counts differ: 2-3 vs 4-5');
  await expect(desk.locator('.detail').getByTestId('report-quote')).toHaveCount(2);
  await expect(desk.locator('.detail')).toContainText('2-3 people');
  await expect(desk.locator('.detail')).toContainText('4-5 people');
  await desk.locator('.detail').getByRole('button', { name: 'How it decided' }).click();
  const trace = desk.getByRole('dialog');
  await expect(trace).toContainText('Similarity');
  await expect(trace).toContainText('Counts differ: 2-3 vs 4-5');
  await context.close();
});
