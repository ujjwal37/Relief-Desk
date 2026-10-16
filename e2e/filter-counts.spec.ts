import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { API } from './ports';

const AUTH = { Authorization: 'Bearer demo-coordinator-token' };
const CLOSED = new Set(['approved', 'dispatched', 'in_progress', 'completed', 'resolved', 'closed']);

async function login(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('rd_tour_done', '1');
    localStorage.setItem('rd_guide_dismissed', '1');
    localStorage.setItem('rd_theme', 'dark');
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
}

async function approveOne(request: APIRequestContext): Promise<string> {
  const cases = (await (await request.get(`${API}/api/requests`, { headers: AUTH })).json()) as {
    id: string;
    status: string;
    flags?: string[];
  }[];
  const open = cases.filter((row) => !CLOSED.has(row.status) && !(row.flags || []).includes('likely_hoax') && !(row.flags || []).includes('hoax'));
  expect(open.length).toBeGreaterThan(0);
  for (const row of open) {
    const matches = await request.get(`${API}/api/requests/${row.id}/matches?top_n=5`, { headers: AUTH });
    if (!matches.ok()) continue;
    const proposals = (await matches.json()) as { match_id?: string }[];
    const matchId = proposals[0]?.match_id;
    if (!matchId) continue;
    const approved = await request.post(`${API}/api/matches/${matchId}/approve`, { headers: AUTH, data: {} });
    if (approved.ok()) return row.id;
  }
  throw new Error('No open case could be approved');
}

test('dispatched and completed chip counts match the rows they show', async ({ page, request }) => {
  const caseId = await approveOne(request);
  await login(page);

  const dispatched = page.getByTestId('filter-dispatched');
  const completed = page.getByTestId('filter-completed');
  await expect(dispatched).toBeVisible();
  await expect.poll(async () => Number(await dispatched.getAttribute('data-count'))).toBeGreaterThan(0);

  const dispatchedCount = Number(await dispatched.getAttribute('data-count'));
  await dispatched.click();
  await expect(page.getByTestId('filter-empty')).toHaveCount(0);
  await expect(page.locator('.case-list-wrap .case-wrap')).toHaveCount(dispatchedCount);
  await expect(page.locator(`[data-case-id="${caseId}"]`)).toBeVisible();

  const done = await request.post(`${API}/api/requests/${caseId}/complete`, { headers: AUTH });
  expect(done.ok()).toBeTruthy();
  await page.reload();
  await page.waitForURL(/\/coordinator\/command/);

  await expect(page.locator(`[data-case-id="${caseId}"]`)).toHaveCount(0);
  await completed.click();
  await expect.poll(async () => Number(await completed.getAttribute('data-count'))).toBeGreaterThan(0);
  const completedCount = Number(await completed.getAttribute('data-count'));
  await expect(page.getByTestId('filter-empty')).toHaveCount(0);
  await expect(page.locator('.case-list-wrap .case-wrap')).toHaveCount(completedCount);
  await expect(page.locator(`[data-case-id="${caseId}"]`)).toBeVisible();

  await page.locator('#coord-search').fill('zzzz-no-such-case');
  await expect(completed).toHaveAttribute('data-count', '0');
  await expect(dispatched).toHaveAttribute('data-count', '0');
  await expect(page.getByTestId('filter-empty')).toBeVisible();
  await expect(page.locator('.case-list-wrap .case-wrap')).toHaveCount(0);

  await page.getByTestId('filter-empty').getByRole('button').click();
  await expect(page.locator('#coord-search')).toHaveValue('');
  await expect(completed).not.toHaveAttribute('data-count', '0');
});
