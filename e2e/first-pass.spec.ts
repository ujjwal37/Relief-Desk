import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';
import { API } from './ports';
import { resetDemo } from './reset-demo';

const SHOTS = '/opt/cursor/artifacts/screenshots';
const AUTH = { Authorization: 'Bearer demo-coordinator-token' };

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

async function clickCoordLink(page: Page, name: string): Promise<void> {
  const nav = page.locator('nav.tabs').getByRole('link', { name, exact: true });
  if (await nav.count() && await nav.isVisible()) {
    await nav.click();
    return;
  }
  const more = page.getByRole('button', { name: 'More', exact: true });
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
      await expect(page.getByRole('link', { name: /I need help/ })).toBeVisible();
      // The coordinator card was replaced by one desk entry. Sign in still opens the login.
      await expect(page.getByRole('link', { name: /I'm a coordinator/ })).toHaveCount(0);
      await expect(page.getByTestId('try-desk')).toBeVisible();
      await expect(page.getByTestId('try-desk')).toContainText('Try the desk');
      // Sign in stays in the footer. Wide screens hide that line; Try the desk is the visible entry.
      const signIn = page.locator('a[href="/coordinator/login"]');
      await expect(signIn).toHaveCount(1);
      if (viewport.width < 900) await expect(signIn).toBeVisible();
      await expect(page.getByText(/Floods bury coordinators in messy reports/)).toBeVisible();
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

      await page.goto('/home');
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
      // At phone width the nav is logo · Ask · menu; the page links live in the menu.
      if (viewport.name !== 'mobile') {
        const commandTab = page.locator('nav.tabs').getByRole('link', { name: 'Command', exact: true });
        await expect(commandTab).toHaveClass(/on/);
        await expect(page.locator('nav.tabs').getByRole('link', { name: 'Situation', exact: true })).toBeVisible();
      }
      await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible();
      // The queue header still carries the synthetic-scenario sentence. The command layout hides it.
      await expect(page.locator('.scenario-visible')).toHaveText('Synthetic scenario inspired by Kerala floods');
      await expect(page.locator('button.case').first()).toBeVisible();
      const hindiCase = page.getByRole('option', { name: /3 children and 2/ });
      await hindiCase.scrollIntoViewIfNeeded();
      await hindiCase.click();
      await page.locator('details.show-report > summary').click();
      await expect(page.locator('.rep-orig')).toContainText('तुरंत नाव भेजो');
      const whyBtn = page.getByRole('button', { name: /Why this team/i });
      await expect(whyBtn).toBeVisible({ timeout: 20_000 });
      await whyBtn.click();
      await expect(page.getByTestId('why-team-popup')).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(page.getByTestId('why-team-popup')).toBeHidden();

      if (viewport.name === 'mobile') {
        await expect(page.locator('button.case').first()).toBeVisible();
        // Below 1200px the map column is closed until Show map.
        if (!(await page.locator('.map-card').isVisible())) {
          await page.getByTestId('map-toggle').click();
        }
        await expect(page.locator('.map-card')).toBeVisible();
        await expect(page.getByRole('button', { name: 'Approve and send' })).toBeVisible();
        await shot(page, 'mobile-case-sheet');
        await noHorizontalOverflow(page);
        await page.locator('.map-card').scrollIntoViewIfNeeded();
        await shot(page, 'mobile-map');
        await noHorizontalOverflow(page);
        // The open map is a fixed sheet over its own Hide map control. Invoke that control, then the queue is clickable again.
        await page.getByTestId('map-toggle').evaluate((node: HTMLButtonElement) => node.click());
        await expect(page.locator('.map-stepper-col.map-open')).toHaveCount(0);
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
      const search = page.locator('#coord-search');
      if (await search.isVisible()) await search.fill(marker);
      const markerRow = page.getByRole('option', { name: new RegExp(marker) });
      const pill = page.getByTestId('new-pill');
      await expect(markerRow.or(pill)).toBeVisible({ timeout: 20_000 });
      if (await pill.isVisible()) await pill.click();
      await expect(markerRow).toBeVisible({ timeout: 12_000 });
      await page.getByRole('option', { name: new RegExp(marker) }).click();
      const approve = page.getByRole('button', { name: 'Approve and send' });
      await approve.scrollIntoViewIfNeeded();
      await expect(approve).toBeEnabled();
      await approve.click();
      await expect(page.locator('.toast')).toContainText('Dispatch approved');
      const mobile = viewport.name === 'mobile';
      await closeCaseSheet(page, mobile);
      await page.getByTestId('tab-dispatched').click();
      const row = page.getByRole('option', { name: new RegExp(marker) });
      await expect(row).toBeVisible();
      await row.click();
      await page.getByRole('button', { name: 'Mark completed' }).click();
      await expect(page.locator('.toast')).toContainText('The team is free again.');
      await closeCaseSheet(page, mobile);
      await page.getByTestId('tab-completed').click();
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
        const noTeam = page.getByTestId('no-team');
        await expect(noTeam.or(page.getByText('No suitable free team nearby'))).toBeVisible();
        if (await noTeam.count()) {
          await expect(noTeam).toContainText(/No free boat|No free team|No suitable/);
          await expect(noTeam.getByText('Your options')).toBeVisible();
        }
        // No grey disabled Approve: the primary action is the chosen no-team option.
        await expect(page.getByRole('button', { name: 'Approve and send' })).toHaveCount(0);
        await shot(page, 'desktop-no-team-free');
      }

      await page.goto('/');
      await page.getByRole('button', { name: 'Settings' }).click();
      await expect(page.getByRole('button', { name: 'Dark', exact: true })).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Malayalam' })).toHaveCount(0);
      await expect(page.getByRole('button', { name: 'Hinglish' })).toBeVisible();
      await page.getByRole('button', { name: 'Hindi' }).click();
      await page.getByRole('button', { name: 'हो गया' }).click();
      await expect(page.getByRole('link', { name: 'मुझे मदद चाहिए' })).toBeVisible();
      await shot(page, `${viewport.name}-hindi`);
      await noHorizontalOverflow(page);
    });
  }
});

async function exhaustBoats(request: APIRequestContext): Promise<void> {
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const resources = await (await request.get(`${API}/api/resources`, { headers: AUTH })).json();
    const free = (resources as Array<{ kind: string; status: string; capacity_remaining: number; lat?: number; lng?: number }>).filter(
      (row) => row.kind === 'boat' && row.status === 'available' && row.capacity_remaining > 0,
    );
    if (free.length === 0) return;
    const targetBoat = free[0];
    const lat = targetBoat.lat != null ? targetBoat.lat + 0.005 : 9.42;
    const lng = targetBoat.lng != null ? targetBoat.lng + 0.005 : 76.41;
    const marker = `E2EEX${attempt}${Date.now().toString().slice(-5)}`;
    const submitted = await request.post(`${API}/api/reports`, {
      data: {
        text: `${2 + attempt} people on a roof at ${marker}, send a boat.`,
        raw_text: `${2 + attempt} people on a roof at ${marker}, send a boat.`,
        channel: 'text',
        lang: 'en',
        location_pin: { lat, lng },
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
    // A remaining boat that matching will not offer for a rooftop rescue cannot fill the gap case.
    if (!boat) return;
    // Approve stays locked until the AI steps finish (or the 45 s rules cap lands).
    let approved = await request.post(`${API}/api/matches/${boat!.match_id}/approve`, { headers: AUTH, data: {} });
    for (let tries = 0; tries < 30 && approved.status() === 409; tries++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      approved = await request.post(`${API}/api/matches/${boat!.match_id}/approve`, { headers: AUTH, data: {} });
    }
    expect(approved.ok(), await approved.text()).toBeTruthy();
  }
  throw new Error('Boats were still free after repeated dispatch');
}
