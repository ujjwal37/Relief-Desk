import { expect, type Locator, type Page } from '@playwright/test';

/** Open the decision panel extras. Hidden content is not visible to Playwright. */
export async function openMoreDetails(page: Page): Promise<void> {
  const more = page.getByRole('button', { name: /Why this team|More details|और विवरण|Aur details/ }).first();
  if (await more.count()) await more.click();
}

/** Open the How it decided technical block. */
export async function openTechnical(dialog: Locator): Promise<void> {
  const btn = dialog.getByRole('button', { name: /Show technical details|तकनीकी विवरण दिखाएँ|Technical details dikhao/ }).first();
  await expect(btn).toBeVisible();
  await btn.click();
  await expect(dialog.getByRole('button', { name: /Hide technical details|तकनीकी विवरण छिपाएँ|Technical details chhupao/ }).first()).toBeVisible();
}
