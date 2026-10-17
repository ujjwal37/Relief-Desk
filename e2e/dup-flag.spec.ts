import { expect, test } from '@playwright/test';
import { API } from './ports';

const AUTH = { Authorization: 'Bearer demo-coordinator-token' };

test('the seeded possible duplicate is obvious on the queue card and explains itself', async ({ page, request }) => {
  await request.post(`${API}/api/demo/full`, { headers: AUTH });
  await page.addInitScript(() => { localStorage.setItem('rd_tour_v2_off', '1'); localStorage.setItem('rd_guide_dismissed', '1'); });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
  const card = page.locator('[data-case-id="DEMO-110"]');
  await expect(card.getByTestId('dup-chip')).toContainText('RD-5422');
  await card.locator('button.case').click();
  await expect(page.getByTestId('dup-review')).toBeVisible();
  await expect(page.getByTestId('dup-level')).toHaveText(/Confidence: (high|medium)/);
  await expect(page.getByTestId('dup-diff').first()).toContainText('plan for 8');
  await expect(page.getByTestId('dup-review')).not.toContainText(/0\.\d/);
});
