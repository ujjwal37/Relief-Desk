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
  await page.addInitScript(() => localStorage.setItem('rd_tour_v2_off', '1'));
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
  const commandTab = page.locator('nav.tabs').getByRole('link', { name: 'Command', exact: true });
  await expect(commandTab).toHaveClass(/on/);
  await expect(page.locator('nav.tabs').getByRole('link', { name: 'Situation', exact: true })).toBeVisible();
  // The first open case can sit far from the Kuttanad teams. Open a Ward 1 case so the lines show minutes.
  await page.locator('[data-case-id="INC-002"] button.case').click();
  await expect(page.locator('.dec-case-sub')).toContainText('Ward 1');
  const teamLine = page.locator('.best-team-banner .team-specs').first();
  await expect(teamLine).toContainText(/km/);
  await expect(teamLine).toContainText(/min/);
  await page.screenshot({ path: path.join(SHOTS, '1366-home-selected.png'), fullPage: false });
  await page.getByRole('button', { name: 'How it decided' }).first().click();
  const how = page.getByRole('dialog', { name: 'How it decided' });
  await expect(how).toBeVisible();
  await expect(how.getByText('Understood the report', { exact: true })).toBeVisible();
  await expect(how.getByText('Found the closest team', { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, '1366-how-it-decided.png'), fullPage: false });
  await openTechnical(how);
  await page.keyboard.press('Escape');
  await expect(how).toBeHidden();
  await openMoreDetails(page);
  const why = page.getByTestId('why-team-popup');
  await expect(why).toBeVisible();
  const eta = why.locator('tbody tr').first().locator('.eta');
  const dist = why.locator('tbody tr').first().locator('.dist');
  await expect(eta).toContainText(/min/);
  await expect(dist).toContainText(/km/);
  const shownKm = ((await dist.innerText()) || '').trim();
  await page.keyboard.press('Escape');
  await expect(why).toBeHidden();
  // With a Maps key the lines are drawn on Google Maps and the schematic SVG is not rendered.
  if (await page.locator('.map-card .rd-google-map').count()) {
    await expect(page.locator('.map-card .rd-google-map')).toBeVisible();
  } else {
    const line = page.locator('.svgmap text.leg').first();
    await expect(line).toBeVisible();
    await expect(line).toContainText(/km/);
    await expect(line).toContainText(/min/);
    await expect(page.locator('.svgmap .pin rect, .svgmap .pin circle').first()).toBeVisible();
    await expect(line).toContainText(shownKm.replace(/\s*km.*/, ''));
  }
  await page.screenshot({ path: path.join(SHOTS, '1366-cases-map.png'), fullPage: false });

  // Situation replaced Overview in the nav. It still shows waiting, dispatched and team counts.
  await page.locator('nav.tabs').getByRole('link', { name: 'Situation', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Situation', exact: true })).toBeVisible();
  const tiles = page.getByTestId('sit-tiles');
  await expect(tiles).toContainText(/\d+/);
  await expect(tiles).toContainText(/waiting/i);
  await expect(tiles).toContainText(/dispatched/i);
  await expect(tiles).toContainText(/completed/i);
  await expect(page.locator('rd-map-provider')).toHaveCount(0);

  // The overview route is still the map-beside-alerts layout. It is no longer linked from the nav.
  await page.goto('/coordinator/overview');
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  const lead = page.locator('.lead-line');
  await expect(lead).toContainText(/\d+ need help now/);
  await expect(lead).toContainText(/\d+ of \d+ teams free/);
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
  // The just-reported strip sits above the map, so the alerts title is lower than the old overview.
  expect(box!.y).toBeLessThan(400);
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
  expect(legs.some((leg) => /Best for RD-|km/.test(leg))).toBeTruthy();
  await page.screenshot({ path: path.join(SHOTS, '1366-teams.png'), fullPage: false });

  await page.goto('/coordinator/agent');
  await expect(page.getByText('Hi, what do you need to know?')).toBeVisible();
  await expect(page.locator('.example')).toHaveCount(3);
  await expect(page.locator('input[name="q"]')).toBeVisible();
  const waiting = page.getByRole('button', { name: /Which cases are still waiting\?/ });
  await expect(waiting).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, '1366-agent.png'), fullPage: false });
  await waiting.click();
  await expect(page.locator('.bubble.user')).toBeVisible();
  await expect(page.locator('.example')).toHaveCount(0);
  await expect(page.locator('form.composer')).toBeVisible();
  await expect(page.locator('.case-link').first()).toBeVisible();
});
