import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test';
import { API } from './ports';

const AUTH = { Authorization: 'Bearer demo-coordinator-token' };
const CLOSED = new Set(['approved', 'dispatched', 'in_progress', 'completed', 'resolved', 'closed']);

async function login(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem('rd_tour_done', '1');
    localStorage.setItem('rd_guide_dismissed', '1');
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/coordinator/login');
  await page.getByRole('button', { name: 'Enter as demo coordinator' }).click();
  await page.waitForURL(/\/coordinator\/command/);
}

async function tabCount(tab: Locator): Promise<number> {
  return Number((await tab.locator('b').innerText()).trim());
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

test('dispatched and completed tab counts match the rows they show', async ({ page, request }) => {
  const caseId = await approveOne(request);
  await login(page);

  const dispatched = page.getByTestId('tab-dispatched');
  const completed = page.getByTestId('tab-completed');
  await expect(dispatched).toBeVisible();
  await expect.poll(async () => tabCount(dispatched)).toBeGreaterThan(0);

  const dispatchedCount = await tabCount(dispatched);
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
  await expect.poll(async () => tabCount(completed)).toBeGreaterThan(0);
  const completedCount = await tabCount(completed);
  await expect(page.getByTestId('filter-empty')).toHaveCount(0);
  await expect(page.locator('.case-list-wrap .case-wrap')).toHaveCount(completedCount);
  await expect(page.locator(`[data-case-id="${caseId}"]`)).toBeVisible();

  await page.locator('#coord-search').fill('zzzz-no-such-case');
  await expect.poll(async () => tabCount(completed)).toBe(0);
  await expect.poll(async () => tabCount(dispatched)).toBe(0);
  await expect(page.getByTestId('filter-empty')).toBeVisible();
  await expect(page.locator('.case-list-wrap .case-wrap')).toHaveCount(0);

  await page.getByTestId('filter-empty').getByRole('button').click();
  await expect(page.locator('#coord-search')).toHaveValue('');
  await expect.poll(async () => tabCount(completed)).toBeGreaterThan(0);
});
