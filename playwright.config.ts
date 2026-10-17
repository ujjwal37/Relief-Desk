import { defineConfig } from '@playwright/test';
import { API, API_PORT, WEB, WEB_PORT } from './e2e/ports';

/**
 * End-to-end checks for the synthetic Kerala demo. Uses the Chrome already on the machine.
 * Its own ports keep a live-AI dev server out of the run; LLM_PROVIDER is cleared so a local
 * model in .env is not used either.
 */
export default defineConfig({
  testDir: 'e2e',
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: 'e2e/results.json' }]],
  use: {
    baseURL: WEB,
    launchOptions: { executablePath: process.env['CHROME_BIN'] || (process.platform === 'win32' ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' : '/usr/bin/chromium') },
    trace: 'retain-on-failure',
    screenshot: 'off',
  },
  webServer: [
    {
      command: `${process.platform === 'win32' ? '.venv\\Scripts\\python.exe' : '.venv/bin/python'} -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: 'services/api',
      env: {
        DEMO_MODE: 'true',
        GOOGLE_MAPS_API_KEY: 'replace-me',
        AI_MODE: 'fallback',
        GEMINI_API_KEY: 'replace-me',
        LLM_PROVIDER: '',
        DEMO_SEED: 'full',
      },
      url: `${API}/healthz`,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: `npx ng serve web --port ${WEB_PORT} --host 127.0.0.1`,
      env: {
        RD_API_TARGET: API,
      },
      url: WEB,
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
});
