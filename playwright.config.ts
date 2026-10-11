import { defineConfig } from '@playwright/test';

/** End-to-end checks for the synthetic Kerala demo. Uses the Chrome already on the machine. */
export default defineConfig({
  testDir: 'e2e',
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: 'e2e/results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:4200',
    channel: 'chrome',
    trace: 'retain-on-failure',
    screenshot: 'off',
  },
  webServer: [
    {
      command: '/tmp/rd-venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: 'services/api',
      url: 'http://127.0.0.1:8000/healthz',
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: 'npx ng serve web --port 4200 --host 127.0.0.1',
      url: 'http://127.0.0.1:4200',
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
});
