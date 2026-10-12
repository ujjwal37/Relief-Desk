import { expect, test, type Page } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const SHOTS = '/opt/cursor/artifacts/screenshots';

test.beforeAll(() => {
  fs.mkdirSync(SHOTS, { recursive: true });
});

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
}

async function closeSheet(page: Page): Promise<void> {
  const back = page.locator('button.sheet-back');
  if (await back.count()) await back.first().click({ force: true });
}

test('map pins stay in sync with the queue and the legend stays visible', async ({ page }) => {
  test.setTimeout(240_000);
  await page.addInitScript(() => localStorage.setItem('rd_tour_done', '1'));
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
      await page.goto('/coordinator/command');
      await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible();
      if (viewport.name === 'mobile') {
        await page.getByRole('tab', { name: 'Map' }).click();
      }
      const legend = page.locator('rd-map-legend');
      await expect(legend).toBeVisible();
      await expect(legend).toContainText('Cases');
      await expect(legend).toContainText('Teams');
      await expect(legend).toContainText('Places');
      await expect(legend).toContainText('Boat team');
      await expect(legend).toContainText('Shelter');
      const casePins = page.locator('.svgmap g.pin[role="button"][aria-label^="Case"]');
      await expect(casePins.first()).toBeVisible();
      if (viewport.name === 'mobile') {
        await page.getByRole('tab', { name: 'Cases' }).click();
      }
      await page.locator('button.case').nth(1).click();
      if (viewport.name === 'mobile') {
        await closeSheet(page);
        await page.getByRole('tab', { name: 'Map' }).click({ force: true });
      }
      const fromQueue = page.locator('.svgmap g.pin[role="button"]:not(.dim)');
      await expect(fromQueue).toHaveCount(1);
      await expect(fromQueue).toHaveAttribute('aria-label', /Case 2,/);
      expect(await page.locator('.svgmap g.pin.dim').count()).toBeGreaterThan(1);
      const other = page.locator('.svgmap').getByRole('button', { name: /^Case 4,/ });
      if (await other.count()) {
        await other.dispatchEvent('click');
        await expect(page.locator('.svgmap g.pin[role="button"]:not(.dim)')).toHaveAttribute('aria-label', /Case 4,/);
        if (viewport.name === 'mobile') {
          await closeSheet(page);
          await page.getByRole('tab', { name: 'Cases' }).click();
        }
        await expect(page.locator('button.case').nth(3)).toHaveAttribute('aria-selected', 'true');
        if (viewport.name === 'mobile') {
          await closeSheet(page);
          await page.getByRole('tab', { name: 'Map' }).click({ force: true });
        }
      }
      await shot(page, `command-pins-${viewport.name}-${theme}`);

      await page.goto('/coordinator/live');
      await expect(page.getByRole('heading', { name: 'Live map' })).toBeVisible();
      await expect(page.locator('rd-map-legend')).toContainText('Cases');
      await shot(page, `live-map-${viewport.name}-${theme}`);

      await page.goto('/coordinator/alerts');
      await expect(page.getByRole('heading', { name: 'Alerts' })).toBeVisible();
      await expect(page.locator('rd-map-legend')).toContainText('Places');
      await shot(page, `alerts-pins-${viewport.name}-${theme}`);
    }
  }
});
