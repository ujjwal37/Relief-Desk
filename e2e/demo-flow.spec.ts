import { expect, test } from '@playwright/test';
import { resetDemo } from './reset-demo';

test.beforeEach(async ({ request }) => {
  await resetDemo(request);
});

test.describe('Demo flow specs (A1-A7, B5/B6, E1-E2)', () => {
  test('greeting "hi" produces no case and stays in thread with gate prompt', async ({ page }) => {
    await page.goto('/report');
    const textarea = page.locator('textarea');
    await expect(textarea).toBeVisible();

    await textarea.fill('hi');
    const sendBtn = page.getByTestId('send-report-btn');
    await sendBtn.click();

    // Check thread reply from gate
    const thread = page.locator('.thread .msg');
    await expect(thread.last()).toContainText("Tell me what's happening and where");

    // Stays on report page (no case created, no navigation to /status)
    expect(page.url()).toContain('/report');
    expect(page.url()).not.toContain('/status');
  });

  test('one-shot send produces receipt and RD-xxxx public code', async ({ page }) => {
    await page.goto('/report');
    const textarea = page.locator('textarea');
    await expect(textarea).toBeVisible();

    await textarea.fill('Kainakary jettyde aduthu veettil vellam kayari, 3 per und, oru ammachi nadakkan pattilla');
    const sendBtn = page.getByTestId('send-report-btn');
    await sendBtn.click();

    await page.waitForURL(/\/status/);
    const rid = page.locator('.rid');
    await expect(rid).toBeVisible();
    const publicCode = (await rid.innerText()).trim();
    expect(publicCode).toMatch(/^RD-/);

    // Receipt card visible with understood facts
    const receipt = page.getByTestId('status-receipt');
    await expect(receipt).toBeVisible();
    const receiptText = await receipt.innerText();
    expect(receiptText).toContain(publicCode);
  });

  test('Share location GPS updates coordinates with Playwright geolocation', async ({ page, context }) => {
    // Set geolocation permission and fake coordinates (Kuttanad: 9.498, 76.338)
    await context.grantPermissions(['geolocation']);
    await context.setGeolocation({ latitude: 9.49806, longitude: 76.33884 });

    await page.goto('/report');
    const gpsBtn = page.getByTestId('share-gps-btn');
    await expect(gpsBtn).toBeVisible();
    await gpsBtn.click();

    // GPS icon should show active/tick state
    await expect(gpsBtn).toHaveClass(/on/);

    const textarea = page.locator('textarea');
    await textarea.fill('Water rising fast, need boat');
    await page.getByTestId('send-report-btn').click();

    await page.waitForURL(/\/status/);
    const rid = page.locator('.rid');
    await expect(rid).toBeVisible();
  });

  test('photo + text submission', async ({ page }) => {
    await page.goto('/report');

    // Create a tiny 1x1 png base64 file buffer to attach
    const buffer = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
      'base64'
    );

    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.getByTestId('attach-photo-btn').click();
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles({
      name: 'rescue.png',
      mimeType: 'image/png',
      buffer,
    });

    // Preview appears
    const preview = page.getByTestId('attached-photo-preview');
    await expect(preview).toBeVisible();

    // Fill message and send
    const textarea = page.locator('textarea');
    await textarea.fill('House flooded up to waist level near church');
    await page.getByTestId('send-report-btn').click();

    await page.waitForURL(/\/status/);
    await expect(page.locator('.rid')).toBeVisible();
  });

  test('offline queue and retry', async ({ page, context }) => {
    await page.goto('/report');
    const textarea = page.locator('textarea');
    await textarea.fill('Family stranded on roof, urgent help needed');

    // Simulate offline
    await context.setOffline(true);

    const sendBtn = page.getByTestId('send-report-btn');
    await sendBtn.click();

    // Offline queue banner appears
    const queueBar = page.getByTestId('offline-queue-bar');
    await expect(queueBar).toBeVisible();
    await expect(queueBar).toContainText('Queued');

    // Textarea still has the user input
    await expect(textarea).toHaveValue('Family stranded on roof, urgent help needed');

    // Restore online
    await context.setOffline(false);

    // Tap retry button
    const retryBtn = page.getByTestId('retry-offline-btn');
    await expect(retryBtn).toBeVisible();
    await retryBtn.click();

    // Successfully arrives on status page
    await page.waitForURL(/\/status/);
    await expect(page.locator('.rid')).toBeVisible();
  });
});
