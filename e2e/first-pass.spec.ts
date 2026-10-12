import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

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

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`) });
}

async function noHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth - root.clientWidth;
  });
  expect(overflow).toBeLessThanOrEqual(2);
}

async function openReportForm(page: Page): Promise<void> {
  await page.goto('/report');
  await page.getByRole('button', { name: 'Prefer a form?' }).click();
  await page.locator('.quick-tiles button').first().click();
  await page.locator('label.field input[type="text"]').fill('Champakulam School');
  await page.locator('label.field input[type="number"]').fill('3');
}

async function sendForm(page: Page): Promise<void> {
  const send = page.getByRole('button', { name: 'Send now' });
  await send.scrollIntoViewIfNeeded();
  await send.click();
}

async function closeCaseSheet(page: Page, mobile: boolean): Promise<void> {
  if (!mobile) return;
  const back = page.getByRole('button', { name: 'Back to cases' });
  if (await back.isVisible()) await back.click();
}

test.describe('public and coordinator demo', () => {
  for (const viewport of VIEWPORTS) {
    test(`${viewport.name} ${viewport.width}x${viewport.height}`, async ({ page, request }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));

      await page.goto('/');
      await expect(page.getByRole('link', { name: 'Report an emergency' })).toBeVisible();
      await expect(page.getByRole('link', { name: /112/ }).first()).toBeVisible();
      await shot(page, `${viewport.name}-home-light`);
      await noHorizontalOverflow(page);
      await page.goto('/nearby');
      await expect(page.getByText('Synthetic scenario inspired by Kerala floods')).toBeVisible();
      await shot(page, `${viewport.name}-nearby`);

      await openReportForm(page);
      await sendForm(page);
      await page.waitForURL(/\/status/);
      await expect(page.getByText('Request sent')).toBeVisible();
      const reportId = new URL(page.url()).searchParams.get('id') || '';
      const token = new URL(page.url()).searchParams.get('token') || '';
      expect(reportId.length).toBeGreaterThan(3);
      const publicCode = (await page.locator('.rid').innerText()).trim();
      expect(publicCode).toMatch(/^RD-/);
      await shot(page, `${viewport.name}-status`);

      await page.goto('/');
      await expect(page.getByText(publicCode)).toBeVisible();
      await expect(page.getByText('Sent. A coordinator will review it.')).toBeVisible();

      const fresh = await page.context().browser()!.newContext({
        viewport: { width: viewport.width, height: viewport.height },
      });
      const findPage = await fresh.newPage();
      await findPage.goto(`/status?find=1`);
      await findPage.locator('#rid').fill(reportId);
      if (token) await findPage.locator('#tok').fill(token);
      await findPage.getByRole('button', { name: 'Find request' }).click();
      await expect(findPage.locator('.rid')).toBeVisible();
      await shot(findPage, `${viewport.name}-find`);
      await fresh.close();

      await page.goto('/report');
      await page.getByRole('button', { name: 'Prefer a form?' }).click();
      await page.locator('.quick-tiles button').first().click();
      await page.locator('label.field input[type="text"]').fill('Nedumudi Boat Jetty');
      await page.locator('label.field input[type="number"]').fill('2');
      await page.context().setOffline(true);
      await sendForm(page);
      await expect(page.getByText('Saved on this phone, will send when online.')).toBeVisible();
      await expect(page.getByText('No network.')).toBeVisible();
      await shot(page, `${viewport.name}-offline`);
      await page.context().setOffline(false);
      await page.waitForTimeout(1500);

      await page.goto('/coordinator/login');
      await expect(page.getByRole('button', { name: 'Enter as demo coordinator' })).toBeVisible();
      await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
      await page.waitForURL(/\/coordinator\/command/);
      await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible();
      await expect(page.getByText('Synthetic scenario inspired by Kerala floods')).toBeVisible();
      await expect(page.locator('button.case').first()).toBeVisible();

      if (viewport.name === 'mobile') {
        await expect(page.getByRole('tab', { name: 'Cases' })).toBeVisible();
        await expect(page.getByRole('tab', { name: 'Map' })).toBeVisible();
        await page.locator('button.case').first().click();
        await expect(page.getByRole('button', { name: 'Back to cases' })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Approve and send' })).toBeVisible();
        await shot(page, 'mobile-case-sheet');
        await noHorizontalOverflow(page);
        await page.getByRole('button', { name: 'Back to cases' }).click();
        await page.getByRole('tab', { name: 'Map' }).click();
        await expect(page.locator('.map-card')).toBeVisible();
        await shot(page, 'mobile-map');
        await noHorizontalOverflow(page);
      } else {
        await shot(page, 'desktop-command');
        await noHorizontalOverflow(page);
      }

      const marker = `E2E${viewport.name}${Date.now().toString().slice(-6)}`;
      const submitted = await request.post(`${API}/api/reports`, {
        data: {
          text: `4 people stranded, need a boat. Synthetic report ${marker}.`,
          raw_text: `4 people stranded, need a boat. Synthetic report ${marker}.`,
          channel: 'text',
          lang: 'en',
          location_pin: { lat: 9.416, lng: 76.411 },
          scenario_id: 'flood',
          idempotency_key: `e2e-${marker}`,
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
      expect(submitted.ok()).toBeTruthy();
      if (viewport.name === 'mobile') await page.getByRole('tab', { name: 'Cases' }).click();
      const search = page.locator('#coord-search');
      if (await search.isVisible()) await search.fill(marker);
      await expect(page.getByRole('option', { name: new RegExp(marker) })).toBeVisible({ timeout: 12_000 });
      await page.getByRole('option', { name: new RegExp(marker) }).click();
      if (viewport.name === 'mobile') {
        await expect(page.getByRole('button', { name: 'Back to cases' })).toBeVisible();
      }
      const approve = page.getByRole('button', { name: 'Approve and send' });
      await expect(approve).toBeEnabled();
      await approve.click();
      await expect(page.locator('.toast')).toContainText('Dispatch Approved');
      const mobile = viewport.name === 'mobile';
      await closeCaseSheet(page, mobile);
      await page.getByRole('button', { name: 'Dispatched' }).click();
      const row = page.getByRole('option', { name: new RegExp(marker) });
      await expect(row).toBeVisible();
      await row.click();
      await page.getByRole('button', { name: 'Mark completed' }).click();
      await expect(page.locator('.toast')).toContainText('The team is free again.');
      await closeCaseSheet(page, mobile);
      await page.getByRole('button', { name: 'Completed' }).click();
      await expect(page.getByRole('option', { name: new RegExp(marker) })).toBeVisible();
      await shot(page, `${viewport.name}-completed`);

      await clickCoordLink(page, 'Teams');
      await expect(page.getByRole('heading', { name: 'Teams' })).toBeVisible();
      await expect(page.getByText(/boat|Naav|medical|Simulated|Nakli/i).first()).toBeVisible();
      await shot(page, `${viewport.name}-teams`);

      await clickCoordLink(page, 'Alerts');
      await expect(page.getByRole('heading', { name: 'Alerts' })).toBeVisible();
      await expect(page.getByText('Resource gap').first()).toBeVisible();
      await shot(page, `${viewport.name}-alerts`);

      await clickCoordLink(page, 'Accuracy report');
      await expect(page.getByRole('heading', { name: 'Accuracy report' })).toBeVisible();
      await expect(page.getByText('First come, first served').first()).toBeVisible();
      await expect(page.getByText('Synthetic reports, our own labels')).toBeVisible();
      await shot(page, `${viewport.name}-accuracy`);

      if (viewport.name === 'desktop') {
        await exhaustBoats(request);
        const gapPlace = `E2EGAP${Date.now().toString().slice(-6)}`;
        const gap = await request.post(`${API}/api/reports`, {
          data: {
            text: 'People on a roof, send a boat. Synthetic.',
            raw_text: 'People on a roof, send a boat. Synthetic.',
            channel: 'text',
            lang: 'en',
            location_pin: { lat: 9.42, lng: 76.41 },
            scenario_id: 'flood',
            idempotency_key: `e2e-gap-${gapPlace}`,
            structured: {
              incident_type: 'rescue',
              place_text: gapPlace,
              people_count: 5,
              hazard: 'water_rising',
              vulnerable: { elderly: true },
              summary: gapPlace,
            },
          },
        });
        expect(gap.ok()).toBeTruthy();
        await page.goto('/coordinator/command');
        await page.locator('#coord-search').fill(gapPlace);
        const gapRow = page.getByRole('option', { name: new RegExp(gapPlace) });
        await expect(gapRow).toBeVisible({ timeout: 12_000 });
        await gapRow.click();
        await expect(page.getByText('No boat free, nearest alternative')).toBeVisible();
        await expect(page.getByText(/Estimated wait \d+ min/)).toBeVisible();
        await shot(page, 'desktop-no-team-free');
      }

      await page.goto('/');
      await page.getByRole('button', { name: 'Settings' }).click();
      await page.getByRole('button', { name: 'Dark', exact: true }).click();
      await expect.poll(() => page.evaluate(() => document.documentElement.getAttribute('data-theme'))).toBe('dark');
      await page.getByRole('button', { name: 'Done' }).click();
      await shot(page, `${viewport.name}-dark`);
      await page.getByRole('button', { name: 'Settings' }).click();
      await page.getByRole('button', { name: 'Light', exact: true }).click();
      await page.getByRole('button', { name: 'Hindi' }).click();
      await page.getByRole('button', { name: 'हो गया' }).click();
      await expect(page.getByRole('heading', { name: 'हम कैसे मदद करें?' })).toBeVisible();
      await shot(page, `${viewport.name}-hindi`);
      await page.getByRole('button', { name: 'सेटिंग्स' }).click();
      await page.getByRole('button', { name: 'Malayalam' }).click();
      await page.getByRole('button', { name: 'കഴിഞ്ഞു' }).click();
      await expect(page.getByRole('heading', { name: 'ഞങ്ങൾക്ക് എങ്ങനെ സഹായിക്കാം?' })).toBeVisible();
      await shot(page, `${viewport.name}-malayalam`);
      await noHorizontalOverflow(page);
    });
  }
});

async function exhaustBoats(request: APIRequestContext): Promise<void> {
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const resources = await (await request.get(`${API}/api/resources`, { headers: AUTH })).json();
    const free = (resources as Array<{ kind: string; status: string; capacity_remaining: number }>).filter(
      (row) => row.kind === 'boat' && row.status === 'available' && row.capacity_remaining > 0,
    );
    if (free.length === 0) return;
    const marker = `E2EEX${attempt}${Date.now().toString().slice(-5)}`;
    const submitted = await request.post(`${API}/api/reports`, {
      data: {
        text: `${2 + attempt} people on a roof at ${marker}, send a boat.`,
        raw_text: `${2 + attempt} people on a roof at ${marker}, send a boat.`,
        channel: 'text',
        lang: 'en',
        location_pin: { lat: 9.4 + attempt * 0.03, lng: 76.35 + attempt * 0.02 },
        scenario_id: 'flood',
        idempotency_key: `e2e-ex-${marker}`,
        structured: {
          incident_type: 'rescue',
          place_text: marker,
          people_count: 2,
          hazard: 'water_rising',
          vulnerable: { child: true },
          summary: marker,
        },
      },
    });
    expect(submitted.ok(), await submitted.text()).toBeTruthy();
    const body = (await submitted.json()) as { request_id: string; dedupe_decision: string };
    expect(body.dedupe_decision).not.toBe('duplicate');
    const matchesRes = await request.get(`${API}/api/requests/${body.request_id}/matches`, { headers: AUTH });
    expect(matchesRes.ok(), await matchesRes.text()).toBeTruthy();
    const matches = (await matchesRes.json()) as Array<{ match_id: string; resource_kind: string; is_fallback?: boolean }>;
    const boat = matches.find((row) => row.resource_kind === 'boat' && !row.is_fallback);
    expect(boat, `free boats left: ${free.map((row) => row.kind).length}`).toBeTruthy();
    const approved = await request.post(`${API}/api/matches/${boat!.match_id}/approve`, {
      headers: AUTH,
      data: {},
    });
    expect(approved.ok(), await approved.text()).toBeTruthy();
  }
  throw new Error('Boats were still free after repeated dispatch');
}
