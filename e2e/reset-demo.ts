import { expect, type APIRequestContext } from '@playwright/test';

const API = 'http://127.0.0.1:8000';
const AUTH = { Authorization: 'Bearer demo-coordinator-token' };

/** Put the running API back to the full flood pack so specs do not share cases or dispatches. */
export async function resetDemo(request: APIRequestContext): Promise<void> {
  const full = await request.post(`${API}/api/demo/full`, { headers: AUTH });
  expect(full.ok(), await full.text()).toBeTruthy();
}
