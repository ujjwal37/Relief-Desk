# WORKDONE.md — Relief Desk work log

## Rules
1. APPEND ONLY. Add new entries at the bottom. Never edit or delete old entries.
2. Every task in `TASKS.md` that changes status must have an entry here in the same commit.
3. Be factual: say what was NOT done or what is flaky. Do not write "works" without saying how you checked.
4. Include exact files touched and commands to reproduce checks.
5. Time in IST. "Who" = Antigravity / Cursor / Ujjwal.
6. If you hit a [VERIFY] item (API name, model id, quota), record what you verified and the source URL.

## Entry template (copy this block)
```
### YYYY-MM-DD HH:MM IST — T-XXX — <who>
- What changed:
- Files:
- How verified (commands / screenshots):
- Notes / risks / not done:
- Next (suggested task id):
```

## Log
### 2026-10-11 — T-000 — Grok Bot (planning)
- What changed: planning docs created (BUILD_BRIEF.md, SETUP.md, TASKS.md, WORKDONE.md), coordinator mockups designed.
- Files: BUILD_BRIEF.md, SETUP.md, TASKS.md, WORKDONE.md, coordinator-*.html/png
- How verified: files reviewed by Ujjwal (pending).
- Notes: no code written yet. Stack is final: Angular + Ionic + Capacitor, FastAPI, Gemini + ADK, Firestore.
- Next: T-001
### 2026-10-11 13:38 IST — T-009 — Antigravity
- What changed: generated and validated synthetic dataset seeds for the flood scenario in fictional city "Riverbend", 12 wards, 60 landmarks with Hindi & Latin aliases, and 40 ground-truth incident seeds; created standalone gazetteer export.
- Files: data/synthetic/flood_v1/seeds.yaml, scripts/validate_seeds.py, scripts/generate_flood_seeds.py, scripts/export_gazetteer.py, data/gazetteer/riverbend_gazetteer.json, TASKS.md
- How verified (commands / screenshots):
  - `python scripts/validate_seeds.py` -> SUCCESS: Seeds dataset is valid! City: Riverbend (Uttar Pradesh), Total Wards: 12, Total Landmarks: 60, Total Incidents: 40.
  - `python scripts/export_gazetteer.py` -> Exported gazetteer to data\gazetteer\riverbend_gazetteer.json with 60 landmarks.
- Notes / risks / not done: all data is strictly synthetic. T-009 acceptance criteria fully met. Ready for T-011 (gazetteer tools) and T-016 / T-017 (benchmark generator).
- Next (suggested task id): T-001 (Repo scaffold by U + C) or T-016 / T-017 (Benchmark generator by A).

### 2026-10-11 13:58 IST — T-001 — Antigravity
- What changed: scaffolded complete monorepo layout adhering to BUILD_BRIEF.md and SETUP.md:
  - ONE Angular PWA at `apps/web` with landing at `/` and lazy-loaded route trees for `public/` (mobile-first PublicLayout, no login) and `coordinator/` (desktop-first CoordinatorLayout).
  - Shared library at `libs/shared` containing core TypeScript models (ExtractedRequest, DedupeDecision, Explanation, VulnerableFlags), SCSS design tokens (Navy, Teal, Urgency bands), and typed ApiClientService.
  - FastAPI backend at `services/api` with `/healthz`, centralized settings, CORS middleware, and unit test suite.
  - Local dev proxy configuration `apps/web/proxy.conf.json` proxying `/api` and `/healthz` to `http://localhost:8000`.
  - GitHub Actions CI workflow in `.github/workflows/ci.yml` verifying Python tests and Angular builds.
- Files: apps/web/**, libs/shared/**, services/api/**, angular.json, package.json, tsconfig.json, .github/workflows/ci.yml, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests` -> 2 passed in 0.54s (verified `/healthz` returns `{"status":"ok"}` without calling Gemini).
  - `ng build shared` -> Built Angular package `shared` to `dist/shared`.
  - `ng build web` -> Built Angular application `web` generating distinct lazy chunks: `landing-component`, `report-component`, `status-component`, `nearby-component`, `coordinator-login-component`, `coordinator-command-component`.
- Notes / risks / not done: monorepo scaffold complete. Capacitor/Ionic CLI wrappers can be added when packaging for native mobile.
- Next (suggested task id): T-004 (FastAPI skeleton schemas by C) and T-006 (Shared lib expansion by C).

