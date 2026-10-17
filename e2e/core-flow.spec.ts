import { expect, test } from '@playwright/test';
import { openTechnical } from './desk-ui';
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
  await context.addInitScript(() => localStorage.setItem('rd_tour_v2_off', '1'));
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
  await expect(trace.getByText('Understood the report', { exact: true })).toBeVisible();
  await openTechnical(trace);
  await expect(trace.getByText('Intake', { exact: true }).first()).toBeVisible();
  await expect(trace.getByText('Matching', { exact: true }).first()).toBeVisible();
  await desk.keyboard.press('Escape');
  await expect(trace).toBeHidden();

  // The decision panel's best-team card carries the measured distance and travel time.
  const best = desk.locator('.best-team-banner').first();
  await expect(best).toContainText(/\d+(\.\d+)? km|No nearby team/);
  await expect(best).toContainText(/min|No nearby team/);
  const approve = desk.getByRole('button', { name: 'Approve and send' });
  await expect(approve).toBeEnabled({ timeout: 20_000 });
  await approve.click();
  await expect(desk.locator('.toast')).toContainText('Dispatch approved');

  await desk.getByTestId('tab-dispatched').click();
  await expect(desk.locator('.card-place-title, .card-line-mid').filter({ hasText: new RegExp(marker) }).first()).toBeVisible();

  await expect(phone.getByText('A team is on the way.')).toBeVisible({ timeout: 20_000 });
  await context.close();
});
