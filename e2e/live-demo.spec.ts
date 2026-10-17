import { expect, test, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { API } from './ports';

const SHOTS = '/opt/cursor/artifacts/screenshots';
const AUTH = { Authorization: 'Bearer demo-coordinator-token' };

test.beforeAll(() => {
  fs.mkdirSync(SHOTS, { recursive: true });
});

async function login(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem('rd_tour_done', '1');
    localStorage.setItem('rd_guide_dismissed', '1');
    localStorage.setItem('rd_theme', 'dark');
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
}

test('live demo runs eight reports and opens a human step popup', async ({ page, request }) => {
  await login(page);
  await expect(page.getByTestId('run-live-demo')).toBeVisible();
  await page.getByTestId('run-live-demo').click();
  await expect(page.getByTestId('demo-progress')).toContainText('Received 8/8', { timeout: 120000 });
  await expect(page.getByTestId('demo-progress')).toContainText('Live demo finished');

  const state = await (await request.get(`${API}/api/demo/live-run`, { headers: AUTH })).json();
  expect(state.received).toBe(8);
  expect(state.status).toBe('done');
  expect(state.joined).toBeGreaterThanOrEqual(2);
  expect(state.flagged).toBeGreaterThanOrEqual(1);
  expect(state.critical).toBeGreaterThanOrEqual(1);

  const cases = await (await request.get(`${API}/api/requests`, { headers: AUTH })).json();
  const hoax = (cases as { flags?: string[]; hoax_reason?: string; raw_text?: string }[]).find((row) =>
    (row.flags || []).includes('likely_hoax') || (row.flags || []).includes('hoax'),
  );
  expect(hoax?.hoax_reason || '').not.toEqual('');
  await expect(page.getByTestId('hoax-chip').first()).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, 'live-demo.png'), fullPage: false });

  if (await page.getByTestId('steps-toggle').first().isVisible()) await page.getByTestId('steps-toggle').first().click();
  await page.getByTestId('stepper-node-intake').click();
  const step = page.getByTestId('step-details');
  await expect(step).toBeVisible();
  await expect(step.getByText('ux.none')).toHaveCount(0);
  await expect(step.getByText('No model ran for this step')).toHaveCount(0);
  await expect(step.getByText('Offline fallback')).toHaveCount(0);
  await step.getByRole('button', { name: /Show prompt and response/ }).click();
  await page.screenshot({ path: path.join(SHOTS, 'step-details-live.png') });
  await page.keyboard.press('Escape');
  await expect(step).toBeHidden();

  await page.locator('details.live-own > summary').click();
  await page.getByTestId('own-report').fill('Judge typed this flood report just now.');
  await page.getByTestId('send-own').click();
  await expect(page.getByTestId('own-error')).toContainText('free limit');
});
