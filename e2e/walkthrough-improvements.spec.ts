import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { API } from './ports';
import { resetDemo } from './reset-demo';

const SHOTS = path.resolve('docs/design/reviews/walkthrough-improvements');
const AUTH = { Authorization: 'Bearer demo-coordinator-token' };

async function login(page: Page) {
  await page.addInitScript(() => { localStorage.setItem('rd_tour_v2_off', '1'); localStorage.setItem('rd_guide_dismissed', '1'); localStorage.setItem('rd_theme', 'light'); });
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/coordinator\/command/);
  await expect(page.locator('[data-case-id="INC-001"]')).toBeVisible();
}

async function fits(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(2);
}

test.beforeEach(async ({ request }) => { fs.mkdirSync(SHOTS, { recursive: true }); await resetDemo(request); });

test('landing report entry works immediately on desktop and mobile', async ({ page }) => {
  for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto('/');
    await page.locator('a.sos').click();
    await expect(page).toHaveURL(/\/report$/);
    await expect(page.locator('.composer textarea')).toBeVisible();
    await expect(page.locator('app-photo-intake label.attach')).toBeVisible();
    await fits(page);
    await page.screenshot({ path: path.join(SHOTS, `report-${viewport.width}.png`) });
  }
});

test('recorded traces, nearby single line, fallback preview and Hindi screenshots', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await login(page);
  await page.locator('[data-case-id="INC-001"] button.case').click();
  await expect(page.locator('.best-team-banner .team-specs').first()).toContainText(/km/);
  await expect(page.locator('.best-team-banner .team-specs').first()).toContainText(/min/);
  await expect(page.locator('.svgmap text.leg')).toHaveCount(1);
  await expect(page.locator('.svgmap text.leg')).toHaveCSS('stroke', 'none');
  await expect(page.locator('.svgmap text.leg').first()).toContainText(/about \d+ min/);
  await fits(page);
  await page.screenshot({ path: path.join(SHOTS, 'coordinator-command.png') });
  await page.getByRole('button', { name: 'How it decided', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'How it decided' });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('.banner.warn')).toHaveCount(0);
  await expect(dialog.getByText('Offline fallback')).toHaveCount(0);
  await expect(dialog.getByText('ux.none')).toHaveCount(0);
  await dialog.getByRole('button', { name: /Show technical details/ }).click();
  const recorded = dialog.locator('app-trace-step .badge').filter({ hasText: 'Recorded replay' });
  const rulesBadges = dialog.locator('app-trace-step .badge').filter({ hasText: 'Rules mode' });
  await expect(dialog.locator('app-trace-step .badge').filter({ hasText: 'Google Maps' })).toHaveCount(1);
  await expect(recorded).toHaveCount(4);
  await expect(dialog.locator('app-trace-step').nth(2)).not.toContainText('Vulnerable flags: Vulnerable flags:');
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.screenshot({ path: path.join(SHOTS, '1366-how-it-decided.png') });
  await dialog.getByRole('checkbox', { name: 'Preview rules fallback' }).check();
  await expect(dialog.getByText('Preview only.', { exact: false })).toBeVisible();
  await expect(rulesBadges).toHaveCount(4);
  await expect(recorded).toHaveCount(0);
  await dialog.getByRole('checkbox', { name: 'Preview rules fallback' }).uncheck();
  await expect(recorded).toHaveCount(4);
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.locator('[data-case-id="INC-001"] button.case').click();
  // INC-001 no longer carries a fake seeded cluster; only real merges show a reports chip.
  await expect(page.locator('[data-case-id="INC-001"]').getByRole('button', { name: '3 reports', exact: true })).toHaveCount(0);
  await expect(page.locator('.cmd')).not.toContainText('kfermvxnjxct');
  await page.screenshot({ path: path.join(SHOTS, 'phone-desk-merged.png') });
  await page.locator('[data-case-id="INC-001"] button.case').click();
  await page.getByRole('button', { name: 'Account menu' }).click();
  await page.locator('.menu').getByRole('button', { name: 'Hindi', exact: true }).click();
  await page.keyboard.press('Escape');
  await expect(page.locator('html')).toHaveAttribute('lang', 'hi');
  await expect(page.locator('.decision-panel').first()).not.toContainText('67.81');
  await page.screenshot({ path: path.join(SHOTS, 'coordinator-hindi.png') });
  await page.setViewportSize({ width: 390, height: 844 });
  await fits(page);
  await page.screenshot({ path: path.join(SHOTS, 'coordinator-mobile-hi.png') });
});

test('surge, medical stock scenario and arrival/completion status updates', async ({ browser, request }) => {
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();
  await login(page);
  // The surge control left the chrome. The desk still shows the run through the live feed.
  const started = await request.post(`${API}/api/demo/simulate-surge`, { headers: AUTH });
  expect(started.status(), await started.text()).toBe(202);
  await expect(page.locator('.surge-note').last()).toContainText('Submitted 5 synthetic reports', { timeout: 40000 });
  const state = await request.get(`${API}/api/demo/surge`, { headers: AUTH });
  expect((await state.json()).submitted).toBe(5);
  const cases = await (await request.get(`${API}/api/requests`, { headers: AUTH })).json();
  expect(cases.every((row: { status: string }) => row.status !== 'dispatched')).toBeTruthy();
  await page.screenshot({ path: path.join(SHOTS, 'live-surge.png') });

  const submitted = await request.post(`${API}/api/reports`, { data: { text: 'Synthetic. 1 person needs food near Cedar ferry desk', location_pin: { lat: 9.44, lng: 76.40 }, structured: { incident_type: 'food', people_count: 1, place_text: 'Cedar ferry desk', hazard: 'none' } } });
  const report = await submitted.json();
  const phone = await context.newPage();
  await phone.goto(`/status?id=${report.report_id}&token=${report.status_token}`);
  const matches = await (await request.get(`${API}/api/requests/${report.request_id}/matches`, { headers: AUTH })).json();
  expect(matches.length).toBeGreaterThan(0);
  // Flagged repeats are no longer folded away, so each surge report gets its own read first.
  await expect.poll(async () => (await (await request.get(`${API}/api/requests/${report.request_id}`, { headers: AUTH })).json()).analysis_status, { timeout: 60000 }).not.toBe('analysing');
  const approved = await request.post(`${API}/api/matches/${matches[0].match_id}/approve`, { headers: AUTH, data: {} });
  expect(approved.ok(), await approved.text()).toBeTruthy();
  await expect(phone.locator('.hero-title')).toContainText('A team is on the way', { timeout: 30000 });
  expect((await request.post(`${API}/api/requests/${report.request_id}/arrived`, { headers: AUTH })).ok()).toBeTruthy();
  await expect(phone.locator('.steps li').nth(2)).toHaveClass(/done/, { timeout: 10000 });
  expect((await request.post(`${API}/api/requests/${report.request_id}/complete`, { headers: AUTH })).ok()).toBeTruthy();
  await expect(phone.locator('.hero-title')).toContainText('Help has arrived', { timeout: 10000 });
  await context.close();
});


test('photo outage stays reviewable and leaves text reporting available', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/report');
  const photo = page.locator('app-photo-intake');
  const tinyPng = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=', 'base64');
  await photo.locator('input[type=file]').setInputFiles({ name: 'synthetic.png', mimeType: 'image/png', buffer: tinyPng });
  await expect(photo.getByRole('button', { name: 'Analyse with Gemini' })).toBeDisabled();
  await photo.getByRole('checkbox', { name: 'This is a synthetic demo image' }).check();
  await photo.getByRole('button', { name: 'Analyse with Gemini' }).click();
  await expect(photo.locator('.error')).toContainText('Photo analysis is unavailable');
  await expect(photo).not.toContainText('AI photo suggestions');
  await fits(page);
  await page.screenshot({ path: path.join(SHOTS, 'photo-offline-fallback.png') });
  await photo.getByRole('button', { name: 'Remove photo' }).click();
  await page.locator('.composer textarea').fill('Synthetic. 4 people stranded at Cedar ferry, need a boat');
  await expect(page.getByRole('button', { name: /Send/  })).toBeEnabled();
});
