import { expect, test } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { openTechnical } from './desk-ui';
import { resetDemo } from './reset-demo';

const SHOTS = '/opt/cursor/artifacts/screenshots';

test.beforeAll(() => {
  fs.mkdirSync(SHOTS, { recursive: true });
});

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

test('command queue, shortcuts, teams, and ask-the-desk at 1366', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);

  const commandTab = page.locator('nav.tabs').getByRole('link', { name: 'Command', exact: true });
  await expect(commandTab).toHaveClass(/on/);
  await expect(page.locator('nav.tabs').getByRole('link', { name: 'Home', exact: true })).toHaveCount(0);
  await expect(page.locator('nav.tabs').getByRole('link', { name: 'Overview', exact: true })).toHaveCount(0);
  await expect(page.locator('nav.tabs').getByRole('link', { name: 'Agent', exact: true })).toHaveCount(0);
  await expect(page.getByTestId('tab-waiting')).toHaveAttribute('aria-selected', 'true');
  for (const id of ['tab-waiting', 'tab-dispatched', 'tab-completed']) {
    await expect(page.getByTestId(id).locator('b')).toHaveText(/^\d+$/);
  }

  await page.getByRole('button', { name: 'Account menu' }).click();
  await expect(page.getByRole('button', { name: 'Dark', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Light', exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');

  const safe = page.locator('[data-case-id="INC-008"] button.case');
  await expect(safe).toBeVisible();
  await safe.click();
  const best = page.locator('.best-team-banner').first();
  await expect(best).toContainText(/\d+(\.\d+)? km/);
  await expect(best).toContainText(/min/);
  await expect(page.locator('app-ai-stepper .stepper-card')).toBeVisible();
  await expect(page.locator('.step-count-title')).toContainText('6 AI steps');
  for (const id of ['intake', 'dedupe', 'triage', 'matching', 'explainer', 'approval']) {
    await expect(page.getByTestId(`stepper-node-${id}`)).toBeVisible();
  }
  await page.screenshot({ path: path.join(SHOTS, '1366-home-selected.png'), fullPage: false });

  await page.getByRole('button', { name: 'How it decided' }).first().click();
  const how = page.getByRole('dialog', { name: 'How it decided' });
  await expect(how).toBeVisible();
  await expect(how.getByText('Understood the report', { exact: true })).toBeVisible();
  await expect(how.getByText('Checked for duplicates', { exact: true })).toBeVisible();
  await expect(how.getByText('Found the closest team', { exact: true })).toBeVisible();
  await expect(how.getByText('Explained the choice', { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, '1366-how-it-decided.png'), fullPage: false });
  await openTechnical(how);
  await expect(how.getByText('Intake', { exact: true }).first()).toBeVisible();
  await expect(how.getByText('Duplicate check', { exact: true }).first()).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(how).toBeHidden();

  await page.getByRole('button', { name: /Why this team/ }).click();
  const why = page.getByTestId('why-team-popup');
  await expect(why).toBeVisible();
  await expect(why.locator('.eta').first()).toContainText(/min/);
  await expect(why.locator('td.dist').first()).toContainText(/km/);
  if (await page.locator('.map-card .rd-google-map').count()) {
    await expect(page.locator('.map-card .rd-google-map')).toBeVisible();
  } else {
    const line = page.locator('.svgmap text.leg').first();
    await expect(line).toBeVisible();
    await expect(line).toContainText(/km|min/);
  }
  await page.keyboard.press('Escape');
  await page.screenshot({ path: path.join(SHOTS, '1366-cases-map.png'), fullPage: false });

  await page.keyboard.press('?');
  const help = page.getByTestId('help-sheet');
  await expect(help).toBeVisible();
  await expect(help).toContainText('Approve and send the suggested team');
  await expect(help).toContainText('Next waiting case');
  await expect(help).toContainText('Undo the last send');
  await page.keyboard.press('Escape');
  await expect(help).toBeHidden();

  const before = await page.locator('.case-wrap.sel').getAttribute('data-case-id');
  await page.keyboard.press('n');
  await expect(page.locator('.case-wrap.sel')).not.toHaveAttribute('data-case-id', before || '');
  await safe.click();
  await expect(page.getByRole('button', { name: /Approve and send/ })).toBeEnabled();
  await page.keyboard.press('a');
  await expect(page.locator('.toast')).toContainText('Dispatch approved');
  await page.keyboard.press('u');
  await expect(page.locator('.toast')).toHaveCount(0);

  await page.locator('#coord-search').fill('forward this');
  const hoax = page.getByRole('option', { name: /forward this to 10 groups/i });
  await expect(hoax).toBeVisible();
  await hoax.click();
  await page.locator('#coord-search').blur();
  await expect(page.getByTestId('dismiss-hoax')).toContainText('Dismiss as hoax');
  await expect(page.getByTestId('not-hoax')).toContainText('Not a hoax');
  await page.getByTestId('not-hoax').click();
  await expect(page.getByTestId('dismiss-hoax')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Approve and send/ })).toBeVisible();
  await page.reload();
  await page.locator('#coord-search').fill('forward this');
  await page.getByRole('option', { name: /forward this to 10 groups/i }).click();
  await page.locator('#coord-search').blur();
  await page.keyboard.press('d');
  await expect(page.locator('.toast')).toContainText('Closed as hoax. Nothing was sent.');

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

  await page.getByRole('button', { name: 'Ask the desk' }).click();
  const ask = page.getByRole('dialog', { name: 'Ask the desk' });
  await expect(ask).toBeVisible();
  await expect(ask.locator('.suggestions button')).toHaveCount(3);
  await expect(ask.locator('input[name="q"]')).toBeVisible();
  await expect(ask.getByRole('button', { name: 'Which cases are still waiting?', exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, '1366-agent.png'), fullPage: false });
  await ask.getByRole('button', { name: 'Which cases are still waiting?', exact: true }).click();
  await expect(ask.locator('.bubble.user')).toContainText('Which cases are still waiting?');
  await expect(ask.locator('form.composer')).toBeVisible();
  await expect(ask.locator('.case-link').first()).toBeVisible();
});
