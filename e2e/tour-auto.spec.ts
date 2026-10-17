import { expect, test, type Page } from '@playwright/test';
import { API } from './ports';

const AUTH = { Authorization: 'Bearer demo-coordinator-token' };

async function demoLogin(page: Page) {
  await page.addInitScript(() => localStorage.setItem('rd_guide_dismissed', '1'));
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
}

for (const vp of [{ name: '1440', width: 1440, height: 900 }, { name: '1280', width: 1280, height: 800 }, { name: '390', width: 390, height: 844 }]) {
  test(`demo login opens the short tour once (${vp.name})`, async ({ page, request }) => {
    await request.post(`${API}/api/demo/full`, { headers: AUTH });
    const before = await (await request.get(`${API}/api/requests`, { headers: AUTH })).json();
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await demoLogin(page);
    const tour = page.getByTestId('tour');
    await expect(tour).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId('tour-skip')).toBeVisible();
    const label = await page.getByTestId('tour-step').textContent();
    const total = Number(/of (\d+)/.exec(label || '')?.[1] || 0);
    expect(total).toBeGreaterThanOrEqual(2);
    expect(total).toBeLessThanOrEqual(6);
    // The card stays inside the viewport on every step.
    for (let i = 1; i < total; i++) {
      const box = await tour.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.y).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(vp.width + 1);
      await page.getByTestId('tour-next').click();
      await expect(page.getByTestId('tour-step')).toContainText(`${i + 1} of ${total}`);
      await expect(page.getByTestId('tour-skip')).toBeVisible();
    }
    await page.getByTestId('tour-skip').click();
    await expect(tour).toBeHidden();
    await page.reload();
    await expect(page.locator('.case-wrap').first()).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(1500);
    await expect(tour).toBeHidden();
    // Read-only: no report sent, nothing approved.
    const after = await (await request.get(`${API}/api/requests`, { headers: AUTH })).json();
    expect(after.length).toBe(before.length);
    expect(after.filter((r: { status: string }) => r.status !== 'new').length).toBe(before.filter((r: { status: string }) => r.status !== 'new').length);
  });
}

test('Esc closes the tour and More > Demo tools replays it', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await demoLogin(page);
  await expect(page.getByTestId('tour')).toBeVisible({ timeout: 15_000 });
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('tour')).toBeHidden();
  await page.locator('.more-btn').click();
  await page.locator('.menu').getByRole('button', { name: /tour/i }).click();
  await expect(page.getByTestId('tour')).toBeVisible({ timeout: 10_000 });
});

test('a normal (non-demo) visit never auto-opens the tour', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('rd_guide_dismissed', '1'));
  await page.setViewportSize({ width: 1440, height: 900 });
  await demoLogin(page);
  await page.keyboard.press('Escape');
  // A fresh tab in the same session, entering Command directly, does not reopen it.
  const second = await page.context().newPage();
  await second.goto('/coordinator/command');
  await second.waitForTimeout(2500);
  await expect(second.getByTestId('tour')).toHaveCount(0);
});
