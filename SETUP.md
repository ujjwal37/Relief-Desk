# SETUP.md — Relief Desk initial setup (Angular + Ionic + FastAPI + Gemini/ADK)

Deadline: submit by 18 Oct 11:59 PM IST, internal target 17 Oct. Items marked **[VERIFY]** must be checked against current docs.
Owner of this file: Ujjwal. Dev agents: Antigravity and Cursor.

## 0. The one rule for AI agents (put this in AGENTS.md / .cursorrules / Antigravity rules)
1. Before any work, read `BUILD_BRIEF.md`, then `TASKS.md`, then the last 20 lines of `WORKDONE.md`.
2. Pick only a task whose status is `TODO` and whose dependencies are `DONE`. Set it to `DOING` in `TASKS.md` and put your tool name as owner.
3. When finished: set status `DONE` in `TASKS.md` (or `BLOCKED` with the reason) and APPEND an entry to `WORKDONE.md`. Never edit old entries.
4. Synthetic data only. No secrets in git. Human approves every dispatch (no auto-dispatch). Small commits, no force-push, no history rewrite.

## 0.1 Product decisions the setup must support (locked 11 Oct)
- Public app Report screen is chat-first (voice/text, Gemini ADK intake agent asks only missing info) with an optional tile/form toggle; both paths produce the same `Request` object. Details: BUILD_BRIEF section 17.
- Scenarios are config packs in `data/scenarios/*.yaml` (flood main, dog-attack second, future crises); never per-scenario screens.
- Confirmation card before submit; only fixed approved safety lines; ≤3-tap fast path, no sign-up, offline retry, SMS fallback.
- News agent is a stretch task (S-001).
- ONE Angular + Ionic + Capacitor PWA (`apps/web`) with role-based lazy routes: public at `/` (no login), coordinator under `/coordinator` (Firebase Auth, seeded synthetic demo account). See BUILD_BRIEF 7.6.
- UI reference: `docs/design/coordinator-*.png`, `docs/design/public-*.png`.

## 1. Prerequisites
| Tool | Version | Install / check |
|---|---|---|
| Git + GitHub account | latest | `git --version` |
| Node.js | current LTS (22.x **[VERIFY]**) | `node -v` (use nvm: `nvm install --lts`) |
| Angular CLI | latest | `npm i -g @angular/cli` then `ng version` |
| Ionic CLI | latest | `npm i -g @ionic/cli` then `ionic -v` |
| Capacitor | via project deps | `npx cap --version` (after scaffold) |
| Python | 3.12 | `python3.12 --version` |
| uv (fast Python env) | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| gcloud CLI | latest | https://cloud.google.com/sdk/docs/install, then `gcloud init` |
| Firebase CLI (Firestore emulator) | latest | `npm i -g firebase-tools`, `firebase login`; emulator needs Java 21+ **[VERIFY]** |
| Playwright (screenshots/e2e) | latest | `npx playwright install chromium` |
| Gemini API key | AI Studio | https://aistudio.google.com/apikey (free tier for dev; production path may be Vertex AI **[VERIFY]**) |
| Google Maps Platform key | Maps JavaScript API | Console > APIs & Services > Credentials |

### Maps key restrictions (do this immediately, never use an unrestricted key)
- Application restriction: HTTP referrers: `http://localhost:*/*`, your Firebase Hosting / Cloud Run domains.
- API restriction: only "Maps JavaScript API" (add Geocoding / Places only if used).
- Set a daily quota cap and a billing budget alert (50/80/100%).
- Dev fallback: Leaflet + OSM if the key is not ready. Keep the map behind a `MapProvider` interface.

### Gemini key hygiene
- Key only in `services/api/.env` (git-ignored) locally and Secret Manager on Cloud Run. Never in Angular code (the browser must call our API, not Gemini).

## 2. GitHub public repo
```bash
mkdir relief-desk && cd relief-desk
git init -b main
# create the repo on github.com (name: relief-desk, Public, MIT or Apache-2.0 licence), then:
git remote add origin git@github.com:<you>/relief-desk.git
```
First commit contains: `README.md`, `LICENSE`, `.gitignore`, `.env.example`, `BUILD_BRIEF.md`, `TASKS.md`, `WORKDONE.md`, `SETUP.md`, `docs/design/` (mockup PNGs: coordinator-*.png, public-*.png), `AGENT_PROMPT.md`. Enable GitHub secret scanning; add gitleaks to pre-commit **[VERIFY]**.

## 3. Monorepo layout
```
relief-desk/
  apps/
    web/             ONE Angular + Ionic + Capacitor PWA
      src/app/public/       lazy route tree, PublicLayout (mobile-first), no login: /report /status /nearby
      src/app/coordinator/  lazy route tree, CoordinatorLayout (desktop-first), Firebase Auth guard: /coordinator/**
      src/app/landing/      "/" with two choices (I need help / I'm a coordinator)
  libs/
    shared/          Angular library: API client, TS models, i18n service, design tokens (SCSS), UI components
  services/
    api/             FastAPI + ADK agents + deterministic tools + tests
  bench/             benchmark harness + synthetic dataset
  data/scenarios/    scenario config packs (flood.yaml, dog_attack.yaml)
  data/synthetic/    synthetic datasets
  docs/design/       mockups (png)
  firebase.json  firestore.rules  firestore.indexes.json
  TASKS.md  WORKDONE.md  BUILD_BRIEF.md  SETUP.md  AGENT_PROMPT.md  AGENTS.md  .env.example
```

## 4. Scaffold commands
### 4.1 Angular workspace: one app + a shared lib
```bash
ng new relief-desk-ws --create-application=false --directory=. --package-manager=npm --skip-git
ng generate application web --routing --style=scss --ssr=false
ng generate library shared --prefix=rd
```
Path alias: in `tsconfig.json`, `"@rd/shared": ["libs/shared/src/public-api.ts"]` (the CLI usually adds a `projects/` path; keep `libs/` by passing `--project-root`/moving and fixing `angular.json` **[VERIFY]**; simplest option is to accept `projects/` and name the folders in this doc accordingly).

### 4.2 Ionic + Capacitor + routes (in the single app)
```bash
ng add @ionic/angular --project=web
npm i @capacitor/core @capacitor/cli @capacitor/geolocation @capacitor/camera
npx cap init "Relief Desk" "app.reliefdesk.demo" --web-dir=dist/web/browser
# later, only when native is needed:
npm i @capacitor/android && npx cap add android
```
Route skeleton (T-046): standalone route trees, lazy-loaded:
```ts
// app.routes.ts
{ path: '', loadComponent: () => import('./landing/landing.page') },
{ path: '', loadChildren: () => import('./public/public.routes') },          // PublicLayout
{ path: 'coordinator', loadChildren: () => import('./coordinator/coordinator.routes') } // CoordinatorLayout + canMatch auth guard
```
Firebase Auth: `npm i firebase @angular/fire`; email/password provider; seed a synthetic demo coordinator via `scripts/seed` (emulator and prod); put the demo credentials in README (demo-only).

PWA: `ng add @angular/pwa --project=web`. Location: use `navigator.geolocation` / Capacitor Geolocation; confirm place on a map pin and keep area-level precision in public views.

### 4.3 Backend
```bash
cd services/api
uv venv --python 3.12 && source .venv/bin/activate
uv pip install fastapi "uvicorn[standard]" pydantic pydantic-settings google-adk google-genai google-cloud-firestore google-cloud-pubsub google-cloud-storage pytest httpx ruff
uv pip freeze > requirements.txt
mkdir -p app/{api,agents,tools} tests
```
Package names for ADK/Gemini SDK **[VERIFY]** (`google-adk`, `google-genai`).

### 4.4 Firestore emulator
```bash
firebase init firestore emulators   # choose Firestore + (optional) Auth emulators
firebase emulators:start --only firestore,auth
```
Set `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080` for the API when developing.

## 5. .env.example (copy to `services/api/.env`; the real file is git-ignored)
```
# --- Gemini / ADK ---
GEMINI_API_KEY=replace-me
GEMINI_MODEL=gemini-2.5-flash        # [VERIFY current model id]
GEMINI_ENABLED=true                   # kill-switch; false => cached/demo responses
GEMINI_DAILY_CALL_CAP=2000
DEMO_MODE=false
# --- Google Cloud ---
GCP_PROJECT_ID=your-project-id
GCP_REGION=asia-south1                # [VERIFY]
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
PUBSUB_TOPIC_ALERTS=alerts
GCS_BUCKET_MEDIA=your-project-relief-desk-media
# --- Maps (browser key goes into the Angular environment file, restricted by referrer) ---
GOOGLE_MAPS_API_KEY=replace-me
GOOGLE_MAPS_MAP_ID=DEMO_MAP_ID
# --- App ---
API_CORS_ORIGINS=http://localhost:4200
SALT_PHONE_HASH=replace-me
RATE_LIMIT_REPORTS_PER_HOUR=10
DEFAULT_LANG=en
SUPPORTED_LANGS=en,hi,hinglish,ta
```
Also create `.gitignore` entries: `.env`, `.venv/`, `node_modules/`, `dist/`, `.angular/`, `*.key`, `android/`, `ios/` (if not needed).

## 6. i18n (multilingual UI and reports)
Languages: English (`en`), हिन्दी (`hi`), Hinglish (`hinglish`, Latin-script Hindi), and one regional language: தமிழ் (`ta`) (swap for বাংলা `bn` if preferred; only the JSON file and font change).

**UI strings.** Use `@ngx-translate/core` (runtime language switch without rebuild; better for a live demo switcher than build-time `@angular/localize`).
```bash
npm i @ngx-translate/core @ngx-translate/http-loader
```
- One JSON per language in `libs/shared/src/i18n/`: `en.json`, `hi.json`, `hinglish.json`, `ta.json`. Same keys in all files, namespaced: `queue.title`, `why.approve`, `alerts.silentZone`, ...
- Never hard-code visible text in templates; always `{{ 'key' | translate }}`. A CI check (`scripts/check-i18n.mjs`) fails if a key is missing in any file.
- A `LanguageService` in `libs/shared` stores the choice in localStorage, sets `<html lang>`, and switches font stacks. The switcher component (EN / हिन्दी / Hinglish / தமிழ்) sits in the coordinator top bar and the public header.
- Fonts: `Inter` + `Noto Sans Devanagari` + `Noto Sans Tamil` (self-host via `@fontsource/*` so rendering works offline); body text min 14 px on dashboard, 16 px on the phone app; check high contrast (WCAG AA).
- Numbers/dates: `Intl.DateTimeFormat` / `Intl.NumberFormat` with `hi-IN` / `ta-IN` locale.

**Free-text reports (user content).** Not translated by JSON. The intake agent (Gemini) detects the language, stores `raw_text` untouched, and produces `text_en` and a translation to the coordinator's selected language (`translations: {en, hi, ta}`). Coordinator UI shows original beside translation, labelled "AI translation". Translations are cached by hash; if translation confidence is low, flag for human review. Explainer agent outputs `text_en` and `text_hi` (and `text_ta` if time permits) with the numeric-consistency check from BUILD_BRIEF section 4.1.
Static safety strings (e.g. 112 banner, fixed first-aid wording for the dog pack) are fixed, human-reviewed translations in the JSON files, never LLM generated at runtime.

## 7. Run locally
```bash
# terminal 1: emulator
firebase emulators:start --only firestore,auth
# terminal 2: API
cd services/api && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
# terminal 3: the single PWA (public at /, coordinator at /coordinator)
ng serve web --port 4200
# demo mode with phone frame: http://localhost:4200/coordinator?demo=1
```
Proxy `/api` to `localhost:8000` with `proxy.conf.json`.

## 8. Sanity checks (all must pass before TASKS T-001 is DONE)
- [ ] `curl localhost:8000/healthz` returns `{"status":"ok"}` (and does not call Gemini).
- [ ] `ng serve web` loads; `/` shows the landing choices, `/report` works without login, `/coordinator` redirects to login; language switcher changes the text of at least 3 labels.
- [ ] Hindi and Tamil glyphs render (no boxes) in both layouts.
- [ ] Python: a 1-call script with your key prints a Gemini reply (`GEMINI_MODEL`), and with `GEMINI_ENABLED=false` returns the cached demo response.
- [ ] Firestore emulator: write and read one doc from the API.
- [ ] Maps key loads a map on localhost and fails from a non-allowed referrer.
- [ ] `git push` works; `gitleaks detect` is clean; `.env` is not tracked (`git ls-files | grep .env` shows only `.env.example`).
- [ ] Agents confirm they have read `TASKS.md` and appended a first line to `WORKDONE.md`.

## 9. Deploy (do last, Day 5 per TASKS.md) — see BUILD_BRIEF section 11
Cloud Run (API, `min-instances=1`, capped `max-instances`), Firebase Hosting for the single PWA with `/api/**` rewrite to Cloud Run, secrets in Secret Manager, budget alerts on.
