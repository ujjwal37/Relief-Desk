import { expect, test, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { resetDemo } from './reset-demo';

const SHOTS = '/opt/cursor/artifacts/screenshots';
const AUTH = { Authorization: 'Bearer demo-coordinator-token' };
const API = 'http://127.0.0.1:8000';

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
] as const;

test.beforeAll(() => {
  fs.mkdirSync(SHOTS, { recursive: true });
});

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

test.afterAll(async ({ request }) => {
  const listed = await request.get(`${API}/api/assist/proposals`, { headers: AUTH });
  if (!listed.ok()) return;
  const body = await listed.json();
  for (const row of body.proposals || []) {
    await request.post(`${API}/api/matches/${row.match_id}/reject`, {
      headers: AUTH,
      data: { reason: 'e2e release' },
    });
  }
});

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

async function noHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(2);
}

async function clickCoordLink(page: Page, name: string): Promise<void> {
  const nav = page.locator('nav.tabs').getByRole('link', { name, exact: true });
  if (await nav.count() && await nav.isVisible()) {
    await nav.click();
    return;
  }
  const more = page.getByRole('button', { name: 'More' });
  if (await more.isVisible()) await more.click();
  else await page.getByRole('button', { name: 'Account menu' }).click();
  await page.locator('.menu').getByRole('link', { name }).click();
}

async function login(page: Page): Promise<void> {
  await page.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
  await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible();
}

test.describe('agents visible', () => {
  for (const viewport of VIEWPORTS) {
    test(`${viewport.name} trace, merge, accuracy, assist`, async ({ page, request }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await login(page);
      await noHorizontalOverflow(page);

      await page.getByRole('button', { name: 'How it decided' }).first().click();
      const dialog = page.getByRole('dialog', { name: 'How it decided' });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByText('Intake', { exact: true }).first()).toBeVisible();
      await expect(dialog.getByText('Duplicate check', { exact: true }).first()).toBeVisible();
      await expect(dialog.getByText('Triage', { exact: true }).first()).toBeVisible();
      await expect(dialog.getByText('Matching', { exact: true }).first()).toBeVisible();
      await expect(dialog.getByText('Explainer', { exact: true }).first()).toBeVisible();
      await expect(dialog.locator('.run-badge')).toHaveText(/Rules|Gemini|Recorded/);
      await expect(dialog.getByText('Offline fallback')).toHaveCount(0);
      await dialog.getByRole('button', { name: 'Show details' }).nth(3).click();
      await expect(dialog.getByText('check_capacity').or(dialog.getByText('No tools')).first()).toBeVisible();
      await shot(page, `${viewport.name}-agent-trace`);
      await noHorizontalOverflow(page);
      await page.keyboard.press('Escape');
      await expect(dialog).toBeHidden();

      await page.getByRole('button', { name: /\d+ reports/ }).first().click();
      const merge = page.getByRole('dialog', { name: 'Reports merged into this case' });
      await expect(merge).toBeVisible();
      await expect(merge.getByText('Not recorded').first()).toBeVisible();
      await shot(page, `${viewport.name}-merged-reports`);
      await page.keyboard.press('Escape');
      await expect(merge).toBeHidden();

      await clickCoordLink(page, 'Accuracy report');
      await expect(page.getByRole('heading', { name: 'Accuracy report' })).toBeVisible();
      await expect(page.getByText('Not measured yet').first()).toBeVisible();
      await expect(page.getByText('gemini-3.5-flash-lite')).toBeVisible();
      await expect(page.getByText('2026-10-12')).toBeVisible();
      await expect(page.getByText('168').first()).toBeVisible();
      await expect(page.getByText('Example data')).toHaveCount(0);
      await expect(page.getByText('First come, first served').first()).toBeVisible();
      await expect(page.getByText('Synthetic reports, our own labels')).toBeVisible();
      await shot(page, `${viewport.name}-accuracy-bars`);
      await noHorizontalOverflow(page);

      await page.getByRole('button', { name: 'Account menu' }).click();
      await page.getByRole('button', { name: 'Dark', exact: true }).click();
      await expect.poll(() => page.evaluate(() => document.documentElement.getAttribute('data-theme'))).toBe('dark');
      await page.locator('.menu-back').click({ position: { x: 4, y: 4 } });
      await shot(page, `${viewport.name}-accuracy-dark`);
      await noHorizontalOverflow(page);
      await page.getByRole('button', { name: 'Account menu' }).click();
      await page.getByRole('button', { name: 'Light', exact: true }).click();
      await page.locator('.menu-back').click({ position: { x: 4, y: 4 } });

      if (viewport.name === 'desktop') {
        const menu = page.locator('button.avatar');
        const closeMenu = () => page.locator('.menu-back').click({ position: { x: 4, y: 4 } });
        await menu.click();
        await expect(page.locator('.menu').getByRole('button', { name: 'Hinglish' })).toHaveCount(0);
        await expect(page.locator('.menu').getByRole('button', { name: 'Malayalam' })).toHaveCount(0);
        await page.locator('.menu').getByRole('button', { name: 'Hindi' }).click();
        await closeMenu();
        await page.goto('/coordinator/command');
        await expect(page.getByRole('button', { name: 'यह कैसे तय हुआ' }).first()).toBeVisible();
        await menu.click();
        await page.locator('.menu').getByTestId('lang-more').click();
        await page.locator('.menu').getByRole('button', { name: 'Hinglish' }).click();
        await closeMenu();
        await expect(page.getByRole('button', { name: 'Ye kaise decide hua' }).first()).toBeVisible();
        await menu.click();
        await page.locator('.menu').getByTestId('lang-more').click();
        await page.locator('.menu').getByRole('button', { name: 'Malayalam' }).click();
        await closeMenu();
        await expect(page.getByRole('button', { name: 'ഇത് എങ്ങനെ തീരുമാനിച്ചു' }).first()).toBeVisible();
        await menu.click();
        await page.locator('.menu').getByRole('button', { name: 'English' }).click();
        await closeMenu();
      }

      const planned = await request.post(`${API}/api/assist/plan`, { headers: AUTH });
      expect(planned.ok()).toBeTruthy();
      const plan = await planned.json();
      expect(plan.proposals.length).toBeGreaterThan(0);
      await page.goto('/coordinator/command');
      await expect(page.getByText(/Staff low: dispatcher suggests \d+ assignments?/)).toBeVisible();
      await page.locator('app-assist-banner').getByRole('button', { name: 'Review' }).click();
      await expect(page.getByText('Nothing is dispatched until you approve')).toBeVisible();
      if (plan.shortages?.length) {
        await expect(page.getByText(/Why only \d+ of \d+\?/).first()).toBeVisible();
      }
      await shot(page, `${viewport.name}-assist`);
      await noHorizontalOverflow(page);
      await page.keyboard.press('Escape');
    });
  }
});
