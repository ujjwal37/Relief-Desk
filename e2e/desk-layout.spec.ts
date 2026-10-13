import { expect, test } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { openMoreDetails, openTechnical } from './desk-ui';
import { resetDemo } from './reset-demo';

const SHOTS = '/opt/cursor/artifacts/screenshots';

test.beforeAll(() => {
  fs.mkdirSync(SHOTS, { recursive: true });
});

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

test('overview, teams, and agent at 1366', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
  const homeTab = page.locator('nav.tabs a').first();
  await expect(homeTab).toHaveText('Home');
  await expect(homeTab).toHaveClass(/on/);
  // The first open case can sit far from the Kuttanad teams. Open a Ward 1 case so the lines show minutes.
  await page.locator('button.case').filter({ hasText: /Ward 1 ·/ }).first().click();
  await expect(page.locator('.facts').first()).toContainText(/km/);
  await expect(page.locator('.facts').first()).toContainText(/min/);
  await page.screenshot({ path: path.join(SHOTS, '1366-home-selected.png'), fullPage: false });
  await page.getByRole('button', { name: 'How it decided' }).first().click();
  const how = page.getByRole('dialog', { name: 'How it decided' });
  await expect(how).toBeVisible();
  await expect(how.getByText('Read the report', { exact: true })).toBeVisible();
  await expect(how.getByText('Picked team', { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, '1366-how-it-decided.png'), fullPage: false });
  await openTechnical(how);
  await page.keyboard.press('Escape');
  await openMoreDetails(page);
  const eta = page.locator('.candidates .eta').first();
  await expect(eta).toContainText(/km/);
  await expect(eta).toContainText(/min/);
  const etas = (await page.locator('.candidates .eta').allTextContents()).map((text) => text.trim());
  // With a Maps key the lines are drawn on Google Maps and the schematic SVG is not rendered.
  if (await page.locator('.map-card .rd-google-map').count()) {
    await expect(page.locator('.map-card .rd-google-map')).toBeVisible();
  } else {
    const line = page.locator('.svgmap text.leg').first();
    await expect(line).toBeVisible();
    await expect(line).toContainText(/km/);
    await expect(line).toContainText(/min/);
    await expect(page.locator('.svgmap .pin path').first()).toBeVisible();
    expect(etas).toContain(((await line.textContent()) || '').trim());
  }
  await page.screenshot({ path: path.join(SHOTS, '1366-cases-map.png'), fullPage: false });

  const overviewNav = page.locator('nav.tabs').getByRole('link', { name: 'Overview', exact: true });
  if (await overviewNav.count() && await overviewNav.isVisible()) {
    await overviewNav.click();
  } else {
    await page.getByRole('button', { name: 'Account menu' }).click();
    await page.locator('.menu').getByRole('link', { name: 'Overview', exact: true }).click();
  }
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  await expect(page.locator('.nums')).toContainText(/\d+ Cases/);
  await expect(page.locator('.nums')).toContainText(/Dispatched/);
  await expect(page.locator('.nums')).toContainText(/Teams/);
  await expect(page.locator('rd-map-provider')).toHaveCount(1);
  await expect(page.locator('.map-stage .rd-schematic circle, .map-stage .rd-google-map')).not.toHaveCount(0);
  await expect(page.locator('.map-stage svg:not(.rd-schematic)')).toHaveCount(0);
  await expect(page.locator('.omap')).toHaveCount(0);
  await expect(page.locator('.map-stage .chips button').first()).toBeVisible();
  const mapTop = await page.locator('.map-stage rd-map-provider').evaluate((el) => getComputedStyle(el).top);
  expect(mapTop).toBe('56px');
  const panel = await page.locator('app-coordinator-alerts').boundingBox();
  expect(panel).not.toBeNull();
  expect(panel!.width).toBeGreaterThan(370);
  expect(panel!.width).toBeLessThan(400);
  expect(panel!.x).toBeGreaterThan(700);
  const alertsOverflow = await page.locator('.alerts-page.list-only').evaluate((el) => getComputedStyle(el).overflowY);
  expect(alertsOverflow).toBe('auto');
  const fits = await page.evaluate(() => document.scrollingElement!.scrollHeight <= window.innerHeight + 1);
  expect(fits).toBeTruthy();
  const alerts = page.getByRole('heading', { name: 'Alerts' });
  await expect(alerts).toBeVisible();
  const box = await alerts.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.y).toBeGreaterThan(40);
  expect(box!.y).toBeLessThan(280);
  await page.screenshot({ path: path.join(SHOTS, '1366-overview.png'), fullPage: false });

  await page.getByRole('link', { name: 'Teams', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Teams' })).toBeVisible();
  await expect(page.getByText(/Stale \d/)).toHaveCount(0);
  await expect(page.locator('.team-map rd-map-provider')).toBeVisible();
  const google = await page.locator('.team-map .rd-google-map').count();
  if (google) {
    expect(google).toBe(1);
  } else {
    expect(await page.locator('.team-map .rd-schematic circle').count()).toBeGreaterThan(2);
  }
  const legs = await page.locator('.list .leg').allTextContents();
  expect(legs.length).toBeGreaterThan(2);
  for (const leg of legs) expect(leg).not.toContain('No nearby team');
  expect(legs.some((leg) => /km/.test(leg))).toBeTruthy();
  await page.screenshot({ path: path.join(SHOTS, '1366-teams.png'), fullPage: false });

  await page.getByRole('link', { name: 'Agent', exact: true }).click();
  await expect(page.getByText('Hi, what do you need to know?')).toBeVisible();
  await expect(page.locator('.example')).toHaveCount(3);
  await expect(page.locator('input[name="q"]')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Which cases are still waiting?', exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, '1366-agent.png'), fullPage: false });
  await page.getByRole('button', { name: 'Which cases are still waiting?', exact: true }).click();
  await expect(page.locator('.bubble.user')).toBeVisible();
  await expect(page.locator('.example')).toHaveCount(0);
  await expect(page.locator('form.composer')).toBeVisible();
  await expect(page.locator('.case-link').first()).toBeVisible();
});
