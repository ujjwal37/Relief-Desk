import { expect, type APIRequestContext } from '@playwright/test';
import { API } from './ports';

const AUTH = { Authorization: 'Bearer demo-coordinator-token' };

/** Put the running API back to the full flood pack so specs do not share cases or dispatches. */
export async function resetDemo(request: APIRequestContext): Promise<void> {
  const health = await request.get(`${API}/api/health/ai`);
  expect(health.ok(), await health.text()).toBeTruthy();
  expect((await health.json()).provider, 'e2e needs the API in AI_MODE=fallback').toBe('fallback');
  const full = await request.post(`${API}/api/demo/full`, { headers: AUTH });
  expect(full.ok(), await full.text()).toBeTruthy();
}
