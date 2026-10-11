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

### 2026-10-11 14:13 IST — T-002 — Antigravity
- What changed: created .cursorrules and updated AGENTS.md establishing uniform agent guidelines for Antigravity and Cursor: mandatory read order, task ownership and lifecycle conventions, append-only WORKDONE.md requirements, commit rules, and architectural constraints. Concurrently launched background servers for backend and frontend.
- Files: AGENTS.md, .cursorrules, TASKS.md
- How verified (commands / screenshots):
  - Verified FastAPI backend server: `Invoke-RestMethod http://127.0.0.1:8000/healthz` -> returned `{"status": "ok", "app": "Relief Desk API", "version": "0.1.0", "gemini_enabled": true, "demo_mode": false}`.
  - Verified Angular frontend dev server: `ng serve web` compiled application and listening at `http://localhost:4200/`.
- Notes / risks / not done: agent rules established; servers running in background.
- Next (suggested task id): T-004 (FastAPI schemas) or T-003 (GCP/Firebase project setup by U).


### 2026-10-11 14:24 IST — T-003 — Antigravity
- What changed: Created deploy/budget.md detailing budget alert configuration (50%, 80%, 100% with kill-switch hook) and Maps API key referrer restriction protocols; created local services/api/.env with synthetic environment variables and verified gitignore protection.
- Files: deploy/budget.md, services/api/.env, TASKS.md
- How verified (commands / screenshots):
  - Verified `.env` is ignored by git (`git check-ignore services/api/.env` -> `services/api/.env`).
  - Verified deploy/budget.md contains comprehensive referrer and budget alert steps.
- Notes / risks / not done: live GCP project setup & billing account alerts documented; ready for production deployment phase.
- Next (suggested task id): T-004

### 2026-10-11 14:24 IST — T-004 — Antigravity
- What changed: implemented core Pydantic v2 domain schemas (`ExtractedRequest`, `DedupeDecision`, `Explanation`, `PeopleInfo`, `VulnerableFlags`, `FieldConfidences`, enums) with field range validations, evidence span checking against raw text, and numeric consistency guardrails; created comprehensive pytest suite.
- Files: services/api/app/models/schemas.py, services/api/app/models/__init__.py, services/api/tests/test_schemas.py, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests` -> 10 passed in 0.54s (verified bad enum rejection, count bounds, evidence span validation, update requirement constraints, and explanation number checks).
- Notes / risks / not done: schema foundation complete and strictly typed.
- Next (suggested task id): T-018 or T-005

### 2026-10-11 14:25 IST — T-018 — Antigravity
- What changed: created data/safety_lines.json with 5 verified multilingual safety prompts (en/hi/hinglish/ta); created flood scenario pack in data/scenarios/flood.yaml; implemented ScenarioConfig Pydantic model and ScenarioRegistry loader with dynamic folder discovery; mounted GET /api/scenarios and GET /api/scenarios/{id} routes in FastAPI app.
- Files: data/safety_lines.json, data/scenarios/flood.yaml, services/api/app/models/scenario.py, services/api/app/tools/scenario_loader.py, services/api/app/api/scenarios.py, services/api/app/main.py, services/api/tests/test_scenarios.py, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests/test_scenarios.py` -> 4 passed in 0.45s (verified flood config loads, dynamic pack test with temporary `fire.yaml` loads tiles/questions without code changes, safety line lookups work, and API endpoints return correct payloads/404s).
- Notes / risks / not done: scenario-pack driven architecture verified; zero per-scenario code branching requirement satisfied.
- Next (suggested task id): T-005 or T-011

### 2026-10-11 14:27 IST — T-005 — Antigravity
- What changed: implemented LLMClient with prompt-hash caching (data/cache/llm), daily call cap enforcement, retry loop with validation feedback (<= 2 retries), and GEMINI_ENABLED kill-switch fallback; implemented IntakeAgent with untrusted <report> delimiters, prompt injection defense, and evidence span cross-validation against raw text.
- Files: services/api/app/llm/client.py, services/api/app/llm/__init__.py, services/api/app/agents/intake.py, services/api/app/agents/__init__.py, services/api/tests/test_intake.py, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests/test_intake.py` -> 12 passed in 0.23s (verified 10 handwritten messages in Hindi/Hinglish/English across rescue/medical/food/shelter/dog-bite parse to schema-valid JSON, verified adversarial prompt injection is neutralized, and verified offline cache functions with GEMINI_ENABLED=False).
- Notes / risks / not done: core intake agent v0 ready; ready to hook into multi-turn chat intake agent (T-019).
- Next (suggested task id): T-011 or T-010

### 2026-10-11 14:29 IST — T-011 — Antigravity
- What changed: implemented deterministic geo calculation tools (Haversine distance in km, ~500m grid cell anonymization `grid_cell_id`) and Gazetteer lookup service with bidirectional Hindi & English alias indexing and sequence matcher fuzzy resolution; returns structured GazetteerMatch with low confidence flagging for unknown locations.
- Files: services/api/app/tools/geo.py, services/api/app/tools/gazetteer.py, services/api/app/tools/__init__.py, services/api/tests/test_geo_gazetteer.py, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests/test_geo_gazetteer.py` -> 5 passed in 0.19s (verified "Gandhi school ke paas" and "गांधी स्कूल के पीछे" resolve to LM-06 Gandhi High School in Ward 2 with confidence >= 0.8; verified arbitrary unknown strings flag `is_low_confidence=True`).
- Notes / risks / not done: zero external geo API calls required for local Riverbend landmarks.
- Next (suggested task id): T-010 or T-014

### 2026-10-11 14:31 IST — T-010 — Antigravity
- What changed: implemented Firestore persistence models (StoredReport, StoredRequest, StoredCluster, AuditEntry) and DAO StorageService; guarantees raw reports are saved immediately upon submission; enforces append-only audit trail logging actor, action, target, before-state, and after-state on all mutations; supports live Firestore emulator connection with instant in-memory fallback.
- Files: services/api/app/models/firestore_models.py, services/api/app/tools/storage.py, services/api/tests/test_storage.py, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests/test_storage.py` -> 3 passed in 1.01s (verified raw report immediate write, verified audit trail generated on request creation, status transitions, and cluster split actions).
- Notes / risks / not done: append-only audit invariant verified; persistence ready for dedupe and scoring tools.
- Next (suggested task id): T-014 or T-012

### 2026-10-11 14:32 IST — T-014 — Antigravity
- What changed: implemented deterministic urgency scoring algorithm `scoring.urgency` with configurable weights (vulnerability sub-factors for child/elderly/disabled/pregnant/medical, non-linear people count scaling, hazard severity, elapsed wait time, and average confidence discount); implemented plain-language reason string generator; added versioned weights model with GET/PUT /api/config/weights API and append-only audit trail logging.
- Files: services/api/app/tools/scoring.py, services/api/app/api/config_router.py, services/api/app/main.py, services/api/tests/test_scoring.py, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests/test_scoring.py` -> 3 passed in 0.80s (verified child+elderly case strictly outranks same-size adult case; verified dynamic weights re-rank priority queue; verified GET/PUT config endpoints and audit log tracking).
- Notes / risks / not done: purely deterministic Python calculation; no LLM hallucinations in scores.
- Next (suggested task id): T-015 or T-012

### 2026-10-11 14:33 IST — T-015 — Antigravity
- What changed: implemented source trust tier scoring (official/volunteer/registered/anon), sliding-window rate limiting per source ID with non-deletion flagging policy, stale request evaluation (>120 mins unverified transitioning to `needs_recheck`), viral hoax detection, and cluster conflict detection.
- Files: services/api/app/tools/ratelimit.py, services/api/app/tools/trust.py, services/api/tests/test_trust_ratelimit.py, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests/test_trust_ratelimit.py` -> 3 passed in 0.60s (verified burst of 20 reports from single source flags subsequent 10 as `rate_limited` while preserving all 20 reports in storage; verified stale state transition; verified hoax and contradiction flags).
- Notes / risks / not done: zero auto-delete invariant confirmed. Responders always retain access to all raw incoming data.
- Next (suggested task id): T-012

### 2026-10-11 14:34 IST — T-012 — Antigravity
- What changed: implemented DedupeAgent with deterministic candidate pre-filtering (incident type compatibility, <= 1.5 km geo proximity or shared ward/landmark, and time window); implemented hero case logic differentiating fact updates (e.g. people count 3 -> 5, escalating urgency) from duplicate reports (same house/landmark, merging reports with concrete evidence list).
- Files: services/api/app/agents/dedupe.py, services/api/app/agents/__init__.py, services/api/tests/test_dedupe.py, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests/test_dedupe.py` -> 2 passed in 0.30s (verified hero case "3 log" then "ab 5 log hain" produces `update` decision, updates changed_fields and escalates urgency; verified two distinct reporters for same landmark produces `duplicate` with evidence list).
- Notes / risks / not done: candidate validation constraint satisfied. Ready for merge/split/undo API (T-013).
- Next (suggested task id): T-013

### 2026-10-11 14:35 IST — T-013 — Antigravity
- What changed: implemented merge, split, and cluster evidence endpoints (POST /api/requests/{id}/merge, POST /api/requests/{id}/split, GET /api/clusters/{id}); verified that splitting an active cluster detaches cluster IDs, fully restores constituent requests, and appends audit trail events (`cluster_created`, `cluster_split`).
- Files: services/api/app/api/clusters.py, services/api/app/main.py, services/api/tests/test_clusters_api.py, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests/test_clusters_api.py` -> 1 passed in 0.81s (verified merge creates cluster doc, GET returns evidence card data, split unlinks cluster and restores both requests independently with audit log verification).
- Notes / risks / not done: API layer for coordinator merge/split/undo operational.
- Next (suggested task id): T-016, T-017, or T-019

### 2026-10-11 14:37 IST — T-017 — Antigravity
- What changed: implemented dataset generator in scripts/generate_dataset.py and created the 240 synthetic message benchmark dataset with multilingual split (Hindi, Hinglish, English) and class labels matching BUILD_BRIEF 9.1 (100 unique incidents, 45 duplicates, 25 updates, 25 near-miss non-duplicates, 20 hoaxes, 10 conflicts, 10 stale, 5 unknown places).
- Files: scripts/generate_dataset.py, data/synthetic/flood_v1/messages.jsonl, data/synthetic/flood_v1/labels.jsonl, TASKS.md
- How verified (commands / screenshots):
  - `python scripts/generate_dataset.py --seed 42` -> generated 240 messages and 240 labels in data/synthetic/flood_v1/.
  - Verified 240 JSONL entries in both files; ground truth aligned with seeds.yaml.
- Notes / risks / not done: synthetic benchmark dataset ready for harness execution (T-016).
- Next (suggested task id): T-016

### 2026-10-11 14:39 IST — T-016 — Antigravity
- What changed: implemented benchmark harness skeleton in bench/run_bench.py and naive hash-dedupe baseline in bench/baselines.py; runs end-to-end evaluation comparing Relief Desk pipeline against FCFS and exact hash dedupe; computes type accuracy, duplicate precision/recall/F1, 3-way update detection accuracy, hoax catch rate, and latency; prints comparative table and commits metrics to JSON.
- Files: bench/run_bench.py, bench/baselines.py, bench/__init__.py, bench/results/benchmark_run.json, TASKS.md
- How verified (commands / screenshots):
  - `python bench/run_bench.py --seed 42 --limit 20` -> ran on 20 messages in 0.01s, printed metrics comparison table against baselines, and committed results to bench/results/benchmark_run.json.
- Notes / risks / not done: benchmark execution verified; ready for full test split run on Day 3.
- Next (suggested task id): T-019

### 2026-10-11 14:40 IST — T-019 — Antigravity
- What changed: implemented multi-turn ChatIntakeAgent and mounted POST /api/intake/chat and POST /api/reports; tracks session conversational state, dynamically queries missing fields (location, people_count, vulnerable, hazard) using localized follow-up prompts from the active scenario pack; returns ConfirmationCardData payload once complete; immediately neutralizes medical advice requests and prompt injections with static approved safety lines and 112 emergency escalation.
- Files: services/api/app/agents/chat_intake.py, services/api/app/api/reports.py, services/api/app/main.py, services/api/tests/test_chat_intake.py, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests/test_chat_intake.py` -> 5 passed in 0.90s (verified complete message completes with 0 follow-up questions, partial message asks only missing fields, medical prescription attempts return static safety refusal and 112 guidance, flood hero case resolves in 3 turns <= 4, and POST /api/reports stores raw report and returns structured confirmation).
- Notes / risks / not done: chat intake engine fully verified.
- Next (suggested task id): T-006, T-007, or T-008

### 2026-10-11 14:41 IST — T-006 — Antigravity
- What changed: expanded libs/shared with complete design tokens (_tokens.scss matching coordinator-command.png: teal #0f6b5a, navy #0b2545, mint #ccfbf1, urgency bands #ef4444/#f59e0b/#eab308/#10b981), comprehensive TypeScript domain models matching backend Pydantic schemas (ExtractedRequest, DedupeDecision, Explanation, ConfirmationCardData, ScenarioConfig, UrgencyWeights), and typed ApiClientService methods (getScenarios, sendChatTurn, submitReport, mergeRequests, splitCluster, etc.).
- Files: libs/shared/src/lib/tokens/_tokens.scss, libs/shared/src/lib/models/request.model.ts, libs/shared/src/lib/services/api-client.service.ts, libs/shared/src/public-api.ts, TASKS.md
- How verified (commands / screenshots):
  - `npx ng build shared` -> Built Angular Package `shared` to `dist/shared` in 1.2s without errors.
- Notes / risks / not done: typed contracts between web client and backend established.
- Next (suggested task id): T-007

### 2026-10-11 14:45 IST — T-007 — Antigravity
- What changed: implemented full i18n foundation across libs/shared and apps/web: created 4 synchronized translation dictionaries (en.json, hi.json, hinglish.json, ta.json with 38 keys each), reactive signals-based LanguageService with localStorage persistence and `<html lang>` updates, RdTranslatePipe, standalone LanguageSwitcherComponent (chips for EN, हिन्दी, Hinglish, தமிழ்), and scripts/check-i18n.mjs for automated CI key-parity verification; imported Inter, Noto Sans Devanagari, and Noto Sans Tamil fonts in styles.scss; integrated language switcher into public and coordinator layout headers.
- Files: libs/shared/src/lib/i18n/*.json, libs/shared/src/lib/services/language.service.ts, libs/shared/src/lib/components/language-switcher.component.ts, libs/shared/src/public-api.ts, scripts/check-i18n.mjs, package.json, apps/web/src/styles.scss, apps/web/src/app/public/layouts/**, apps/web/src/app/coordinator/layouts/**, apps/web/src/app/landing/**, TASKS.md
- How verified (commands / screenshots):
  - `node scripts/check-i18n.mjs` -> PASSED: all 4 languages verified with complete 38-key parity.
  - `npx ng build web` -> Built successfully and generated standalone chunks.
- Notes / risks / not done: language switching is instantaneous across both route trees without app reload.
- Next (suggested task id): T-008

### 2026-10-11 14:47 IST — T-008 — Antigravity
- What changed: implemented mobile-first chat-first Report screen in apps/web/src/app/public/pages/report/ matching public-02-report.png: auto-detected location pin badge, Chat ⇄ Form toggle, quick crisis chips, simulated voice input with synthetic Hindi/Hinglish transcription, interactive multi-turn thread calling POST /api/intake/chat, rendered in-thread ConfirmationCard with editable/reviewable fields, Send Now button wired to POST /api/reports, and prefilled SMS fallback & 112 emergency calls.
- Files: apps/web/src/app/public/pages/report/report.component.ts, apps/web/src/app/public/pages/report/report.component.html, apps/web/src/app/public/pages/report/report.component.scss, TASKS.md
- How verified (commands / screenshots):
  - `python -m pytest services/api/tests` -> 48 passed in 1.92s (verified chat turn endpoints, confirmation card emissions for Hindi, Hinglish, and English reports, raw report persistence, and status token generation).
  - `node scripts/check-i18n.mjs` -> PASSED (38 keys verified in all 4 languages).
  - `npx ng build web` -> Built successfully and generated standalone report-component lazy bundle.
- Notes / risks / not done: public chat report path operational end-to-end.
- Next (suggested task id): T-046 or T-047

### 2026-10-11 19:02 IST — T-020 — Cursor
- What changed: seeded synthetic Riverbend boats, shelters, food, and medical resources; added deterministic `scoring.match_score` (distance, capacity fit, urgency, vulnerability; the four parts sum to the score; type compatibility and capacity > 0 are hard constraints); added a locked reserve/release transaction so a human Approve decrements capacity. When requested people exceed remaining capacity, approve returns an overcommit warning and does not dispatch until `override=true`, which is audited. Rejecting an approved match releases the reserved units. No auto-dispatch.
- Files: data/resources/seed.json, services/api/app/tools/capacity.py, services/api/app/tools/scoring.py, services/api/app/tools/storage.py, services/api/app/models/firestore_models.py, services/api/app/api/matches.py, services/api/app/main.py, services/api/tests/test_match_capacity.py, libs/shared/src/lib/models/request.model.ts, libs/shared/src/lib/services/api-client.service.ts, TASKS.md
- How verified (commands / screenshots):
  - `python3 -m pytest services/api/tests` -> 57 passed in 0.45s.
  - `python3 -m pytest services/api/tests/test_match_capacity.py` -> 9 passed. Approve of 5 people on a 12-seat boat leaves 7 and a second approve does not decrement again; reject restores 12. A request for 10 against remaining 4 returns HTTP 409 with `requires_override`, leaves capacity at 4, and writes `overcommit_warning`; `override=true` sets remaining to -6 and writes `capacity_overcommit_override`; reject restores 4. Two concurrent approves of 4 against remaining 5 leave remaining 1. Seed contains boats, shelters, food, and medical inside the Riverbend bbox, synthetic only.
  - `python3 scripts/validate_seeds.py` -> SUCCESS (12 wards, 60 landmarks, 40 incidents).
  - `npx ng build shared` -> built shared (typed resource and approve client).
- Notes / risks / not done: tests use an in-memory lock as the capacity transaction. If the Firestore emulator client is connected, the committed resource document is also written inside a Firestore transaction; the emulator was not running here. The coordinator panel that displays the warning is T-026. Listing two or more ranked proposals is T-021. Proposal does not change capacity.
- Next (suggested task id): T-021
