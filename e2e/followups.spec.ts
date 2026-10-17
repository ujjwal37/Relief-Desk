import { expect, test, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { resetDemo } from './reset-demo';

const SHOTS = '/opt/cursor/artifacts/screenshots';

test.beforeAll(() => {
  fs.mkdirSync(SHOTS, { recursive: true });
});

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

async function login(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('rd_tour_done', '1');
    localStorage.setItem('rd_guide_dismissed', '1');
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
}

test('step popup, case card, counts, alerts, and Gemini call counter', async ({ page }) => {
  await login(page);

  await expect(page.getByTestId('ai-health')).toContainText('Rules mode');
  await expect(page.getByTestId('gemini-calls')).toHaveCount(0);
  await expect(page.getByText('Offline fallback')).toHaveCount(0);
  await expect(page.getByText('ux.none')).toHaveCount(0);

  const batch = page.getByTestId('batch-counters');
  await expect(batch).toContainText(/\d+\s+waiting/);
  await expect(batch).toContainText(/\d+\s+dispatched/);

  await page.locator('details.show-report > summary').click();
  const english = page.getByTestId('ai-english-full');
  await expect(english).toBeVisible();
  await expect(english).not.toContainText('person(s) needing');
  await expect(page.locator('.field-grid-arrow')).toBeHidden();
  await page.locator('.decision-panel').screenshot({ path: path.join(SHOTS, 'case-card.png') });

  const options = page.getByRole('option');
  const optionCount = await options.count();
  for (let i = 0; i < Math.min(optionCount, 12); i++) {
    await options.nth(i).click();
    if (await page.getByTestId('team-why').count()) break;
  }
  const why = page.getByTestId('team-why');
  await expect(why).toBeVisible();
  await expect(why).not.toContainText('—');
  await expect(why).toContainText(/\d+(\.\d+)?\s*km/);

  await expect(page.getByTestId('stepper-node-matching')).toContainText('Team');
  await expect(page.getByTestId('stepper-node-matching')).toContainText('Rules');
  await expect(page.getByTestId('stepper-node-approval')).toContainText('You');

  await page.getByTestId('stepper-node-intake').click();
  const step = page.getByTestId('step-details');
  await expect(step).toBeVisible();
  await expect(step.locator('.headline')).not.toHaveText('');
  await expect(step.locator('.chips li').first()).toBeVisible();
  await expect(step.locator('.why')).toContainText('Why');
  await expect(step.locator('.note')).not.toContainText('Offline fallback');
  await expect(step.locator('.note')).not.toContainText('ux.none');
  await step.getByTestId('show-prompt').click();
  await expect(step.getByTestId('prompt-and-response')).toBeVisible();
  await expect(step.getByTestId('step-tools')).toBeVisible();
  await expect(step.getByTestId('prompt-and-response').locator('pre').last()).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, 'step-popup.png') });
  await page.keyboard.press('Escape');

  await page.getByTestId('stepper-node-matching').click();
  await expect(page.getByTestId('step-details').locator('.note')).toHaveText('Google Maps');
  await page.keyboard.press('Escape');
  await page.getByTestId('stepper-node-approval').click();
  await expect(page.getByTestId('step-details').locator('.note')).toHaveText('You');
  await expect(page.getByTestId('step-details').locator('.headline')).toContainText('Nothing is sent until you approve');
  await page.keyboard.press('Escape');

  await page.getByRole('link', { name: 'Teams', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Teams' })).toBeVisible();
  const strip = page.locator('.strip');
  const freeBtn = strip.getByRole('button', { name: /^Free \d+$/ });
  const busyBtn = strip.getByRole('button', { name: /^Busy \d+$/ });
  await expect(freeBtn).toBeVisible();
  await expect(busyBtn).toBeVisible();
  const freeN = Number((await freeBtn.innerText()).match(/\d+/)?.[0]);
  const busyN = Number((await busyBtn.innerText()).match(/\d+/)?.[0]);
  expect(freeN).toBeGreaterThan(0);
  expect(busyN).toBeGreaterThanOrEqual(0);
  await expect(page.locator('.head-sub')).toHaveText(`${freeN} free · ${busyN} busy`);
  const row = page.getByTestId('team-row').first();
  await row.click();
  await expect(page.getByTestId('team-detail')).toBeVisible();
  await expect(page.locator('[data-testid="team-card"][data-selected="true"]')).toBeVisible();

  await page.goto('/coordinator/alerts');
  await expect(page.getByRole('heading', { name: 'Alerts' })).toBeVisible();
  const kinds = await page.locator('.alert-row .kind').evaluateAll((nodes) =>
    nodes.map((node) => (node.getAttribute('data-kind') || '') + '|' + (node.textContent || '').replace(/\s+/g, ' ').trim()),
  );
  expect(kinds.some((row) => row.startsWith('spike|'))).toBe(true);
  expect(kinds.some((row) => row.includes('Report spike'))).toBe(true);
  expect(kinds.some((row) => row.startsWith('silent_zone|'))).toBe(true);
  expect(kinds.some((row) => row.includes('Silent zone'))).toBe(true);
  expect(kinds.some((row) => row.startsWith('conflict|'))).toBe(true);
  expect(kinds.some((row) => row.includes('Conflict'))).toBe(true);
  expect(kinds.some((row) => row.startsWith('stale|'))).toBe(true);
  expect(kinds.filter((row) => row.includes('Resource gap')).length).toBeLessThan(kinds.length);
  const ages = await page.locator('.alert-row .age').allTextContents();
  expect(ages.length).toBeGreaterThan(1);
  for (const age of ages) {
    expect(age.trim()).toMatch(/min ago|h ago|Just now/);
  }
});

test('demo login shows an error when demo mode is off', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  await page.route('**/api/health', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'ok', demo_mode: false }),
  }));
  await page.goto('/coordinator/login');
  await expect(page.getByTestId('demo-login-error')).toBeVisible();
  await expect(page.getByTestId('demo-login-error')).toContainText('Demo mode is disabled');
  await expect(page.getByRole('button', { name: 'Enter as demo coordinator' })).toHaveCount(0);
});

test('demo login shows an error when the server returns 403', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  await page.route('**/api/auth/demo-login', (route) => route.fulfill({
    status: 403,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'Demo login is off' }),
  }));
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await expect(page.getByTestId('demo-login-error')).toContainText('Demo mode is disabled');
});

test('reporter sees progress and a queue confirmation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/reports', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 600));
    await route.continue();
  });
  await page.goto('/report');
  await page.getByRole('button', { name: 'Prefer a form?' }).click();
  await page.locator('.quick-tiles button').first().click();
  await page.locator('label.field input[type="text"]').fill('Kainakary jetty lane');
  await page.locator('label.field input[type="number"]').fill('3');
  await page.getByRole('button', { name: 'Send now' }).click();
  await expect(page.getByTestId('ai-analysing')).toBeVisible();
  await page.waitForURL(/\/status/);
  await expect(page.getByTestId('queued-confirm')).toContainText('coordinator queue');
});
