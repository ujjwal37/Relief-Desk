import { expect, type Locator, type Page } from '@playwright/test';

/**
 * Open the Why this team dialog.
 * The ranking table's More details control is hidden; Why this team opens the same dialog.
 */
export async function openMoreDetails(page: Page): Promise<void> {
  const more = page.getByRole('button', { name: /Why this team|यह टीम क्यों|Yeh team kyon|More details/ }).first();
  await expect(more).toBeVisible({ timeout: 20_000 });
  await more.click();
}

/** The duplicate-check evidence sits behind Show details on that step. */
export async function openDedupeDetails(dialog: Locator): Promise<Locator> {
  const step = dialog.locator('app-trace-step').filter({ hasText: /Duplicate check|डुप्लिकेट/ }).first();
  const show = step.getByRole('button', { name: /Show details|विवरण दिखाएँ|Details dikhao/ });
  await expect(show).toBeVisible();
  await show.click();
  return step;
}

/** The citizen's words sit behind Show report on the decision panel. */
export async function openShowReport(page: Page): Promise<void> {
  const details = page.locator('details.show-report').first();
  if (!(await details.count())) return;
  if ((await details.getAttribute('open')) !== null) return;
  await details.locator('summary').click();
}

/** Open the How it decided drawer. */
export async function openHowItDecided(page: Page): Promise<Locator> {
  await page.getByRole('button', { name: /How it decided|यह कैसे तय हुआ|Ye kaise decide hua|ഇത് എങ്ങനെ തീരുമാനിച്ചു/ }).first().click();
  const dialog = page.getByRole('dialog', { name: /How it decided|यह कैसे तय हुआ|Ye kaise decide hua|ഇത് എങ്ങനെ തീരുമാനിച്ചു/ });
  await expect(dialog).toBeVisible();
  return dialog;
}

/** Open the How it decided technical block. */
export async function openTechnical(dialog: Locator): Promise<void> {
  const btn = dialog.getByRole('button', { name: /Show technical details|तकनीकी विवरण दिखाएँ|Technical details dikhao/ }).first();
  if (await btn.count()) await btn.click();
}

/** Waiting / Dispatched / Completed tab count, from the number the tab shows. */
export async function queueTabCount(tab: Locator): Promise<number> {
  const text = ((await tab.locator('b').innerText()) || '').replace(/[^\d]/g, '');
  return Number(text || '0');
}
