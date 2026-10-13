/**
 * E2E runs its own API and web server, so a developer's live-AI servers on 8000 and 4200
 * are never reused. The API here always starts with AI_MODE=fallback.
 */
export const API_PORT = 8100;
export const WEB_PORT = 4300;
export const API = `http://127.0.0.1:${API_PORT}`;
export const WEB = `http://127.0.0.1:${WEB_PORT}`;
