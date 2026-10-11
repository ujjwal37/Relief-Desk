# Relief Desk

**Decision support for crisis responders: who to help first, and why.**
A multilingual crisis-reporting and coordination prototype built for the Google Cloud AI Builder Cup 2026 (theme: Sustainability & Social Impact).

> **Prototype. Not an emergency service. In an emergency call 112.** All data in this repository is synthetic.

Live demo: `<URL to add>` | Demo video: `<link to add>` | Coordinator demo login: see Demo section

## Demo
One PWA, two roles. Open the live URL: **"I need help / report"** needs no login. **"I'm a coordinator"** goes to `/coordinator/login`.
Demo coordinator (synthetic, demo-only): email `demo-coordinator@reliefdesk.internal` / password `KeralaRelief2026!` (created by `scripts/seed.py`).
Side-by-side demo mode: add `?demo=1` on desktop.

## The problem
In floods and other disasters, coordinators are buried in noisy messages: the same request arrives many times, updates get lost, rumours mix with real calls, and the most vulnerable people can be lost in a first-come-first-served queue. Reports of past floods in Kerala (2018) and Chennai (2015) describe duplicate entries, stale requests and a hoax. `<add sources before publishing>`

## What it does
- **Report** by voice or text in Hindi, Hinglish or English from a phone, see what the system understood, track status.
- **Understand:** Gemini (via Google ADK agents) turns a message into a validated structured request (type, place, people, vulnerable people, urgency) and keeps the original message with confidence scores.
- **Dedupe:** merges duplicates with visible evidence; treats "now 5 people" as an update that raises urgency; every merge can be undone or split.
- **Rank:** vulnerability-weighted urgency with a plain-language reason, adjustable weights and an audit log.
- **Match:** seeded boats, shelters, food and medical resources, scored on distance, capacity, urgency and vulnerability. Capacity drops as dispatches are approved, and over-commitment is warned. **A human coordinator approves every dispatch.**
- **Protect:** trust levels, rate limits, conflict flags and stale-request rechecks flag problems for a human; nothing is auto-deleted.
- **Public map:** area-level incidents only. No names, phone numbers or exact addresses.

Designed around scenario packs: flood is the main demo; a dog-attack pack (synthetic) is optional; other crises can be added by configuration.

## How it works
```
Phone app / Coordinator dashboard (Firebase Hosting)
        -> Cloud Run API (FastAPI)
              -> ADK agents: Intake, Dedupe/Anomaly, Matching, Explainer (Gemini)
              -> Deterministic tools: scoring, geo, capacity, trust, rate limits
              -> Firestore (reports, requests, resources, matches, audit)
```
The model understands language; plain code does the scoring, distances and capacity. Model output is always schema-validated and never trusted blindly.

## Benchmark (synthetic, our own labels)
Run `python bench/run_bench.py` (see `bench/`). Results on `<N>` synthetic Hinglish/Hindi/English messages (dev/test split, seed 42):

| Metric | Relief Desk | Baseline |
|---|---|---|
| Extraction accuracy (type / place / people) | _ | keyword _ |
| Duplicate precision / recall | _ | hash-dedupe _ |
| Duplicate-vs-update accuracy | _ | n/a |
| Critical cases in top-k | _ | first-come-first-served _ |
| Hoax/spam catch rate | _ | none |

These numbers are from synthetic data and do not claim real-world accuracy. `<fill from bench/results/latest.md>`

## Safety and limitations
- Decision support only; humans approve every dispatch; no auto-dispatch or auto-delete.
- Synthetic data only; no real personal data is collected or stored.
- Dog-attack pack shows only fixed official first-aid wording; no medical advice.
- Language and place understanding can be wrong; the UI shows the original message and confidence.
- Per-user rate limits and spend caps protect the public endpoint.

## Run locally
```bash
cp .env.example .env     # add your own settings; never commit secrets

# API, from services/api
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# PWA, from the repo root. The workspace has more than one project, so name it:
npx ng serve web --port 4200
npx ng build web

# synthetic coordinator account
python scripts/seed.py

# put the running API back to the synthetic Kerala demo (seeds load again)
python scripts/reset_demo
```
`ng build` without `web` fails because the Angular workspace has two projects. Use `npx ng build web`.

### Live Gemini versus the recorded demo

`DEMO_MODE=true` (the default in `.env.example`) never calls Gemini. Intake, the chat that feeds intake, dedupe comparison, and the match explainer use cached or deterministic replies. CI and the recorded demo stay on this path.

To call Gemini, set these only in `.env`. Do not commit a key:

```
DEMO_MODE=false
GEMINI_ENABLED=true
GEMINI_API_KEY=your-key
```

A timeout, an error, a placeholder key (`replace-me`), or `GEMINI_ENABLED=false` uses the same deterministic replies. The case AI reading shows Gemini or Offline fallback for the path that produced it.

## Deploy
See `deploy/cloudrun.md` (Cloud Run + Firebase Hosting/Auth + Firestore).

## Built with
Google Gemini, Google ADK, Cloud Run, Firebase (Hosting, Auth), Firestore, Secret Manager, `<Pub/Sub if used>`, Angular, Ionic, Capacitor, FastAPI. Built with help from AI coding tools (Antigravity, Cursor).

## Roadmap (not built)
Hourly local-news watch, weather alerts, SMS/WhatsApp intake, offline sync, more Indian languages.

## License
`<choose>`
