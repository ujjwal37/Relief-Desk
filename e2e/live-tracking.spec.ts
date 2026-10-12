import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const SHOTS = '/opt/cursor/artifacts/screenshots';
const AUTH = { Authorization: 'Bearer demo-coordinator-token' };
const API = 'http://127.0.0.1:8000';
const BOAT = 'RES-BOAT-01';

test.beforeAll(() => {
  fs.mkdirSync(SHOTS, { recursive: true });
});

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
}

async function reset(request: APIRequestContext): Promise<void> {
  const res = await request.post(`${API}/api/demo/reset`, { headers: AUTH });
  expect(res.ok()).toBeTruthy();
}

async function submitCase(request: APIRequestContext, marker: string, lat: number, lng: number) {
  const res = await request.post(`${API}/api/reports`, {
    data: {
      text: `4 people stranded, need a boat. Synthetic report ${marker}.`,
      raw_text: `4 people stranded, need a boat. Synthetic report ${marker}.`,
      channel: 'text',
      lang: 'en',
      location_pin: { lat, lng },
      scenario_id: 'flood',
      idempotency_key: `live-${marker}`,
      structured: {
        incident_type: 'rescue',
        place_text: marker,
        people_count: 4,
        hazard: 'water_rising',
        vulnerable: { child: true },
        summary: marker,
      },
    },
  });
  expect(res.ok()).toBeTruthy();
  return res.json() as Promise<{ report_id: string; request_id: string; status_token: string }>;
}

test('dispatch, simulated ETA, complete, then the free team is proposed again', async ({ page, request }) => {
  await reset(request);
  const marker = `LIVE${Date.now().toString().slice(-6)}`;
  const filed = await submitCase(request, marker, 9.5, 76.41);
  const matches = await request.get(`${API}/api/requests/${filed.request_id}/matches`, { headers: AUTH });
  expect(matches.ok()).toBeTruthy();
  const proposals = await matches.json();
  const boat = proposals.find((row: { resource_id: string }) => row.resource_id === BOAT) || proposals[0];
  expect(boat?.match_id).toBeTruthy();
  const approved = await request.post(`${API}/api/matches/${boat.match_id}/approve`, { headers: AUTH, data: {} });
  expect(approved.ok()).toBeTruthy();

  const resources = await request.get(`${API}/api/resources`, { headers: AUTH });
  expect(resources.ok()).toBeTruthy();
  const team = (await resources.json()).find((row: { id: string }) => row.id === boat.resource_id);
  expect(team?.share_token).toBeTruthy();
  const teamName = team.name as string;

  const tracking = async () => {
    const row = await request.get(`${API}/api/reports/${filed.report_id}/tracking?token=${filed.status_token}`);
    expect(row.ok()).toBeTruthy();
    return row.json();
  };
  const before = await tracking();
  expect(before.visible).toBeTruthy();
  expect(before.simulated).toBeTruthy();
  expect(before.distance_km).toBeGreaterThan(0);
  for (let i = 0; i < 4; i += 1) {
    const step = await request.post(`${API}/api/demo/tracking/step`, { headers: AUTH });
    expect(step.ok()).toBeTruthy();
  }
  const after = await tracking();
  expect(after.simulated).toBeTruthy();
  expect(after.distance_km).toBeLessThan(before.distance_km);
  expect(after.team_name).toBe(teamName);

  await page.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
  await page.context().grantPermissions(['geolocation']);
  await page.context().setGeolocation({ latitude: 9.48, longitude: 76.41 });

  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);

  const themes = ['light', 'dark'] as const;
  const viewports = [
    { name: 'desktop', width: 1440, height: 900 },
    { name: 'mobile', width: 390, height: 844 },
  ] as const;

  for (const viewport of viewports) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    for (const theme of themes) {
      await page.evaluate((mode) => localStorage.setItem('rd_theme_mode', mode), theme);
      await page.goto('/coordinator/live');
      await expect(page.getByRole('heading', { name: 'Live map' })).toBeVisible();
      await expect(page.getByText('Simulated movement').first()).toBeVisible();
      await shot(page, `live-map-${viewport.name}-${theme}`);

      await page.goto(`/team/${team.id}?token=${team.share_token}`);
      await expect(page.getByRole('button', { name: 'Share my location' })).toBeVisible();
      await page.getByRole('button', { name: 'Share my location' }).click();
      await expect(page.getByText('Location sharing is on')).toBeVisible();
      await shot(page, `team-share-${viewport.name}-${theme}`);

      await page.goto(`/status?id=${filed.report_id}&token=${filed.status_token}`);
      await expect(page.getByTestId('citizen-track')).toBeVisible();
      await expect(page.getByTestId('citizen-track')).toContainText(teamName);
      await expect(page.getByTestId('citizen-track')).toContainText('Simulated movement');
      await shot(page, `citizen-track-${viewport.name}-${theme}`);
    }
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.evaluate(() => localStorage.setItem('rd_theme_mode', 'light'));
  await page.goto(`/team/${team.id}?token=${team.share_token}`);
  for (const label of ['Accepted', 'On the way', 'Arrived']) {
    const button = page.getByRole('button', { name: label, exact: true });
    await expect(button).toBeVisible();
    await button.click();
  }
  await page.getByRole('button', { name: 'Mark completed' }).click();
  await page.locator('input[name="people"]').fill('3');
  await page.getByRole('radio', { name: 'No' }).check();
  await page.locator('form.outcome').getByRole('button', { name: 'Mark completed' }).click();
  await expect(page.locator('.state')).toHaveText('Free');

  const freed = await request.get(`${API}/api/resources`, { headers: AUTH });
  const freeTeam = (await freed.json()).find((row: { id: string }) => row.id === team.id);
  expect(freeTeam.status).toBe('available');
  expect(freeTeam.assigned_request_id == null).toBeTruthy();

  const nextMarker = `NEXT${Date.now().toString().slice(-6)}`;
  const next = await submitCase(request, nextMarker, freeTeam.lat, freeTeam.lng);
  const nextMatches = await request.get(`${API}/api/requests/${next.request_id}/matches`, { headers: AUTH });
  expect(nextMatches.ok()).toBeTruthy();
  const nextRows = await nextMatches.json();
  const again = nextRows.find((row: { resource_id: string }) => row.resource_id === team.id);
  expect(again).toBeTruthy();
  expect(again.explanation).toContain('free since');
  expect(again.explanation).toContain('km away');

  const plan = await request.post(`${API}/api/assist/plan`, { headers: AUTH });
  expect(plan.ok()).toBeTruthy();
  const planned = await plan.json();
  const proposed = (planned.proposals || []).find((row: { resource_id: string }) => row.resource_id === team.id);
  expect(proposed).toBeTruthy();
  expect(proposed.why || '').toMatch(/free since|km away/);
  expect(proposed.dispatched).toBeFalsy();

  await page.goto('/coordinator/command');
  const review = page.locator('app-assist-banner').getByRole('button', { name: 'Review', exact: true });
  await expect(review).toBeVisible();
  await review.click();
  await expect(page.getByRole('dialog')).toContainText(teamName);
  await expect(page.getByText('Nothing is dispatched until you approve')).toBeVisible();
  await shot(page, 'assist-proposes-free-team');
});
