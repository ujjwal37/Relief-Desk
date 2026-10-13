import { expect, test } from '@playwright/test';
import { resetDemo } from './reset-demo';

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

/**
 * The judge's minute: a phone report shows on the desk, the decision is visible,
 * a person approves a team, and the phone says help is on the way.
 */
test('phone report is approved and the reporter sees help on the way', async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 1366, height: 768 },
    geolocation: { latitude: 9.498, longitude: 76.339 },
    permissions: ['geolocation'],
  });
  await context.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  const desk = await context.newPage();
  const phone = await context.newPage();
  const marker = `House 44 River Lane ${Date.now().toString().slice(-6)}`;

  await desk.goto('/coordinator/login');
  await desk.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await desk.waitForURL(/\/coordinator\/command/);
  await expect(desk.getByRole('heading', { name: 'Cases' })).toBeVisible();

  await phone.goto('/report');
  await phone.getByRole('button', { name: 'Prefer a form?' }).click();
  await phone.locator('.quick-tiles button').first().click();
  await phone.locator('label.field input[type="text"]').fill(marker);
  await phone.locator('label.field input[type="number"]').fill('4');
  await phone.getByRole('button', { name: 'Send now' }).click();
  await phone.waitForURL(/\/status/);
  await expect(phone.getByText('Sent. A coordinator will review it.')).toBeVisible();

  await desk.locator('#coord-search').fill(marker);
  const row = desk.getByRole('option', { name: new RegExp(marker) });
  await expect(row).toBeVisible({ timeout: 20_000 });
  await row.click();

  await desk.getByRole('button', { name: 'How it decided' }).first().click();
  const trace = desk.getByRole('dialog', { name: 'How it decided' });
  await expect(trace).toBeVisible();
  await expect(trace.getByText('Intake', { exact: true }).first()).toBeVisible();
  await expect(trace.getByText('Matching', { exact: true }).first()).toBeVisible();
  await desk.keyboard.press('Escape');
  await expect(trace).toBeHidden();

  await expect(desk.locator('.facts').first()).toContainText(/\d+(\.\d+)? km/);
  await expect(desk.locator('.facts').first()).toContainText(/min|No nearby team/);
  const leg = desk.locator('.svgmap text.leg').first();
  await expect(leg).toBeVisible();
  await expect(leg).toContainText(/km/);
  const approve = desk.getByRole('button', { name: 'Approve and send' });
  await expect(approve).toBeEnabled({ timeout: 20_000 });
  await approve.click();
  await expect(desk.locator('.toast')).toContainText('Dispatch approved');

  await desk.getByRole('link', { name: 'Dispatched', exact: true }).click();
  await expect(desk.getByRole('option', { name: new RegExp(marker) })).toBeVisible();

  await expect(phone.getByText('A team is on the way.')).toBeVisible({ timeout: 20_000 });
  await context.close();
});
