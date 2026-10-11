# TASKS.md — Relief Desk, 12–17 Oct 2026 (IST)

UI design references live in `docs/design/` (see `docs/design/README.md` for the screen-to-task map); each UI task row ends with its design file.

## Rules (read before every task)
1. Read `BUILD_BRIEF.md` and `SETUP.md` first. Pick a task with status `TODO` whose dependencies are `DONE`.
2. Change its Status here (`TODO` → `DOING` → `DONE` / `BLOCKED`) and APPEND an entry to `WORKDONE.md` after EACH task (same commit).
3. Don't start a task from a later section while an earlier core task is `TODO` unless Ujjwal says so.
4. A task is DONE only when its acceptance criteria were checked and the check is written in WORKDONE.md.
5. Synthetic data only, human approves every dispatch, no secrets in git, small commits, no history rewrite.
6. Stretch tasks (S-xxx) start only after core demo (T-001…T-0xx marked CORE) is DONE.

Owners: **A** = Antigravity, **C** = Cursor, **U** = Ujjwal. Status: TODO / DOING / DONE / BLOCKED.
Cut lines: end 13 Oct dedupe works or simplify; end 14 Oct matching + dashboard done or drop stretch; **15 Oct end = feature freeze**; 16 Oct stability + video; 17 Oct submit.

**Architecture decisions (locked 11 Oct, updated 11 Oct pm):** ONE Angular + Ionic + Capacitor PWA at `apps/web` with role-based lazy routes: public at `/` (no login, mobile-first `PublicLayout`), coordinator under `/coordinator` (Firebase Auth login, desktop-first `CoordinatorLayout`); shared libs in `libs/shared` inside the same project (T-046, T-047). Demo-mode phone frame (T-054), hosted URL (T-048), QR (T-049). public Report screen is chat-first (voice/text, Gemini ADK intake agent asks only missing info) with an optional tile/form toggle; both paths emit the same `Request` object. Scenarios (flood main, dog-attack second, future crises) are config packs (T-018), never separate screens. Confirmation card before submit (T-039), fixed approved safety lines only (T-045), fast path ≤3 taps / no sign-up / offline retry / SMS fallback (T-028, T-029). Stack: Angular + Ionic + Capacitor (single PWA), FastAPI, Gemini/ADK, Firestore, Google Maps. UI reference: `docs/design/coordinator-*.png`, `docs/design/public-*.png`. News agent = STRETCH (S-001) only.

Core demo (~2:45): public report → intake agent → dedupe merge → vulnerability-weighted ranking → "why this match" panel → human Approve. Then benchmark vs first-come-first-served, flood main scenario, dog-attack pack (config only), news-agent stretch.

## Day 0 / Mon 12 Oct — Foundation + intake
| ID | Task | Owner | Status | Depends | Acceptance criteria |
|---|---|---|---|---|---|
| T-001 | Repo scaffold: ONE Angular+Ionic+Capacitor PWA at `apps/web` (lazy route trees `public/` and `coordinator/`, shared code in `libs/shared`) + `services/api`, .gitignore, .env.example, push public repo | U + A | DONE | – | SETUP.md section 8 sanity checks pass; repo public; CI lint runs |
| T-002 | Agent rules file (AGENTS.md/.cursorrules) pointing to TASKS.md + WORKDONE.md | U + A | DONE | T-001 | Both tools show they read it; first WORKDONE entry exists |
| T-003 | GCP + Firebase project, budget alerts (50/80/100%), Maps key restricted, Gemini key in .env | U + A | DONE | – | Budget alert email test; Maps key blocked from other referrer |
| T-004 | FastAPI skeleton: `/healthz`, config, pydantic schemas (`ExtractedRequest`, `DedupeDecision`, `Explanation`) | C + A | DONE | T-001 | `pytest` passes; schema rejects bad enums |
| T-005 | **CORE** Intake agent v0 (ADK + Gemini): text → `ExtractedRequest`, validation, ≤2 retries, `needs_human_review` fallback, cache, GEMINI_ENABLED kill-switch | A | DONE | T-004 | 10 hand-written hi/hinglish/en messages parse to schema-valid JSON; injection test string is ignored; cache hit works offline |
| T-006 | Shared lib (`libs/shared`, imported by both route trees of `apps/web`): design tokens (teal #0f6b5a, navy, mint, urgency red/amber), API client, models | C + A | DONE | T-001 | Tokens match `coordinator-command.png`; API client typed Design: `docs/design/public-contact-sheet.png`, `docs/design/coordinator-command.png` |
| T-007 | **i18n foundation**: `@ngx-translate`, `LanguageService`, JSON files en/hi/hinglish/ta, language switcher component, Noto Sans Devanagari + Tamil fonts, CI key-parity check | C + A | DONE | T-006 | Switcher changes ≥10 labels in both layouts (public and coordinator); Hindi/Tamil glyphs render; `check-i18n` fails when a key is missing Design: `docs/design/public-06-report-hi.png`, `docs/design/coordinator-command-hi.png` |
| T-046 | **CORE** App shell + routing in `apps/web`: landing screen at `/` with two big choices "I need help / report" (no login → `/report`, `/status`, `/nearby`) and "I'm a coordinator" (→ `/coordinator/login`); separate layout shells: `PublicLayout` (mobile-first, Ionic, 360–480 px) and `CoordinatorLayout` (desktop-first, 1440x900); each route tree lazy-loaded (`loadChildren`) | C + A | DONE | T-001, T-006 | Landing shows both choices in en/hi; public routes need no login; `/coordinator/**` redirects to login when signed out; build output shows separate lazy chunks | Design: `docs/design/public-01-home.png`, `docs/design/coordinator-command.png`|
| T-047 | **CORE** Coordinator auth: Firebase Auth (email/password) login screen, route guard on `/coordinator/**`, role claim `coordinator`, **seeded demo coordinator account (synthetic email + password) created by `scripts/seed`**; credentials written in README demo section; API verifies the ID token on coordinator endpoints | C + A + U | DONE | T-003, T-046, T-004 | Signed-out user cannot reach `/coordinator` or call coordinator API (401 test); demo login works on local emulator and deployed site; password is demo-only and not reused anywhere | Design: `docs/design/coordinator-command.png` |
| T-008 | Public route tree `/report` (mobile-first layout, inside `apps/web`) **chat-first Report screen** per `public-02-report.png`: voice/text chat, language chips, auto-location pin; chat calls the intake agent (T-019); all submissions call `POST /api/reports` and yield the shared `Request` object | A | DONE | T-005, T-006, T-019 | Hindi, Hinglish, English report each returns a confirmation card shown in the chat thread Design: `docs/design/public-02-report.png` |
| T-009 | Synthetic dataset seeds: fictional city, ~12 wards, ~60 landmarks with hi/Latin aliases, 40 incident seeds (YAML) | U + A | DONE | – | `data/synthetic/flood_v1/seeds.yaml` validates against schema |
| T-018 | **CORE** Scenario config pack schema + loader (`data/scenarios/*.yaml`: incident type, follow-up questions per type, urgency rules, resource types, fixed safety lines ids, tile list). Ship `flood` pack. Both apps and API read it; no per-scenario screens or code branches | C + A | DONE | T-004 | Schema validation test; adding a dummy `fire.yaml` makes a new tile + questions appear with zero code change |
| T-019 | **CORE** Chat intake agent (ADK + Gemini): multi-turn, infers incident type, asks ONLY missing fields (location, people count, vulnerable, injuries) using the active scenario pack questions, replies in user's language, repeats back, emits confirmation card payload; never gives advice beyond fixed safety lines | A | DONE | T-005, T-018 | Transcripts: complete message → 0 follow-ups; partial message → only missing fields asked; injection/medical-advice request refused with fixed line; ≤4 turns for the flood hero case |

## Day 1 / Tue 13 Oct — Dedupe, ranking, trust
| ID | Task | Owner | Status | Depends | Acceptance criteria |
|---|---|---|---|---|---|
| T-010 | **CORE** Firestore persistence: reports, requests, clusters, audit (append-only), emulator tests | C + A | DONE | T-004 | Report stored raw immediately; audit entry on every state change |
| T-011 | **CORE** Gazetteer + geo tools (haversine, 500 m cell id, fuzzy place match) | C + A | DONE | T-009 | "Gandhi school ke paas" resolves to seeded landmark; unknown place → low confidence flag |
| T-012 | **CORE** Dedupe agent + candidate pre-filter (geo/time/type) + `DedupeDecision` validation (target id must be in candidates) | A | DONE | T-005, T-010, T-011 | Hero case: "3 log" then "ab 5 log hain" → `update` (urgency up, history kept); two reporters same house → `duplicate` with evidence list |
| T-013 | **CORE** Merge / split / undo API + evidence card data | C + A | DONE | T-012 | Split restores both requests; audited |
| T-014 | **CORE** `scoring.urgency` (vulnerability-weighted, people, hazard, wait, confidence discount) + versioned weights config + `PUT /api/config/weights` | C + A | DONE | T-010 | Unit tests: child+elderly outranks same-size adult case; changing weight changes rank; reason string produced |
| T-015 | Trust levels, rate limit, stale → `needs_recheck`, conflict + hoax flags (flag only, never delete) | A | DONE | T-010 | Burst of 20 copies from one source flagged `rate_limited`; nothing deleted |
| T-016 | Benchmark harness skeleton: dataset loader, FCFS baseline, hash-dedupe baseline, `run_bench.py` writing JSON | A | DONE | T-009 | `python bench/run_bench.py --seed 42` runs on 20 msgs and prints a metrics table |
| T-017 | Dataset generator (templates + Gemini paraphrase), 240 msgs hi/hinglish/en with noise + labels | A + U | DONE | T-009 | `labels.jsonl` present; class counts per BUILD_BRIEF 9.1; U reviews random 20% and logs disagreement rate |

## Day 2 / Wed 14 Oct — Matching, explainer, coordinator dashboard
| ID | Task | Owner | Status | Depends | Acceptance criteria |
|---|---|---|---|---|---|
| T-020 | **CORE** Resources seed (boats/shelters/food/medical) + `scoring.match_score` + capacity reserve/release transaction + overcommit warning | C + A | DONE | T-014, T-011 | Approve decrements capacity; overcommit shows warning and requires override (audited) |
| T-021 | **CORE** Matching agent (orchestration only) + `GET /api/requests/{id}/matches` with breakdown | A | DONE | T-020 | Returns ≥2 proposals with distance/capacity/urgency/vulnerability parts that sum to the score |
| T-022 | **CORE** Explainer agent (≤2 sentences, en + hi, numeric-consistency check, template fallback) | A | DONE | T-021 | Any number in text not in breakdown triggers fallback; test with forged output |
| T-023 | **CORE** Coordinator layout shell under `/coordinator` (lazy-loaded, desktop-first, behind auth guard from T-047): top bar (alerts, scenario switcher, language switcher), 3-pane layout per `coordinator-command.png` | C + A | DONE | T-006, T-007 | Layout matches mockup at 1440x900; works in EN/HI; public bundle does not include coordinator code (lazy chunk check) Design: `docs/design/coordinator-command.png` |
| T-024 | **CORE** Ranked queue (score chips, merged-duplicate badges, vulnerable icons) + request detail (raw message beside AI reading + confidence bars + AI translation label) | C + A | DONE | T-023, T-014 | Selecting request updates centre + right panes Design: `docs/design/coordinator-command.png` |
| T-025 | **CORE** Map panel (Google Maps JS via MapProvider, cluster markers, resource pins) | A | DONE | T-023, T-003 | Clusters show counts; click selects request Design: `docs/design/coordinator-command.png` |
| T-026 | **CORE** "Why this match" panel + Approve / Edit / Reject wired to API | C + A | DONE | T-021, T-022, T-024 | Approve updates capacity bar and queue status live; Reject logs reason Design: `docs/design/coordinator-command.png` |
| T-027 | Weights drawer (sliders re-rank live) + dedupe evidence/undo UI | C + A | DONE | T-013, T-014, T-024 | Slider change re-orders queue within 1 s Design: `docs/design/coordinator-command.png` |
| T-028 | **Offline + fallback path** in public app: save report locally when offline and auto-retry (idempotency key), "Send by SMS" (prefilled `sms:` link with compact code text) and "Call 112" buttons always visible; SMS text parsed by the same intake agent | A | DONE | T-008, T-010 | Airplane-mode test: report queued, sent on reconnect once only; SMS link opens prefilled text Design: `docs/design/public-02-report.png` |
| T-029 | **Fast path ≤3 taps, no sign-up**: Home big Report button → speak/tap answer chip → "Send now"; location auto-filled; anonymous session; tap-count test recorded | C + A | DONE | T-008, T-038, T-039 | Documented walkthrough with ≤3 taps and no login screen; large tap targets ≥48 px, contrast AA Design: `docs/design/public-01-home.png` |

## Day 3 / Thu 15 Oct — Public map, anomalies, benchmark, deploy, FREEZE
| ID | Task | Owner | Status | Depends | Acceptance criteria |
|---|---|---|---|---|---|
| T-030 | Public nearby map (area cells only) + status page (received → matched → help on the way) | A | DONE | T-008, T-010 | API test: no names/phones/exact addresses in `/api/public/cells` Design: `docs/design/public-05-nearby.png`, `docs/design/public-04-status.png` |
| T-031 | Anomaly engine: spike, silent-zone, resource gap, conflict, stale + `GET /api/alerts` + Alerts view per `coordinator-alerts.png` | C | DONE | T-015, T-023 | Seeded spike and silent zone appear as alerts with reasons Design: `docs/design/coordinator-alerts.png` |
| T-032 | Benchmark full run on test split: all metrics from BUILD_BRIEF 9.3, Relief Desk vs FCFS vs hash-dedupe, results committed | A | DONE | T-017, T-012, T-014 | One command produces `bench/results/*.json` + markdown table; 3 failure examples captured |
| T-033 | Benchmark view in coordinator app per `coordinator-benchmark.png` reading the results JSON | C | DONE | T-032, T-023 | Numbers on screen equal JSON; "Synthetic data, our own labels" visible Design: `docs/design/coordinator-benchmark.png` |
| T-034 | Voice path v0 (Gemini audio or Speech-to-Text) with 5–8 synthetic voice notes | A | DONE | T-008 | Hindi voice note → transcript → request; transcript stored |
| T-035 | Ta/hi/hinglish translation of free-text reports (Gemini, cached, "AI translation" label) shown in queue/detail | A | DONE | T-007, T-005 | Original + translation side by side; low-confidence flagged |
| T-036 | Deploy v1: Cloud Run API + Firebase Hosting (single site for the one PWA, `/api/**` rewrite), secrets in Secret Manager, seed script | U + C | TODO | T-026, T-030 | Public URL works from phone on mobile data; `/healthz` OK |
| T-037 | **FEATURE FREEZE (end of day)**; tag `rc1` | U | TODO | T-036 | No new feature branches after this |
| T-048 | **Hosted URL**: single Firebase Hosting URL for the PWA (HTTPS, mic + geolocation permissions work), stable and short; recorded in README, deck and WORKDONE | U + C | TODO | T-036 | Opens `/` on phone with mobile data; `/coordinator/login` works on laptop; HTTPS padlock; URL checked again after final deploy |
| T-049 | **QR code for slides**: PNG + SVG QR of the hosted URL (and `/report` deep link), generated by script `scripts/make_qr` and committed in `docs/qr/`; placed on deck by U | C + U | TODO | T-048 | Phone camera scan opens the public landing/report page; QR regenerated if URL changes |
| T-038 | **Tile/form toggle** on Report screen (Chat ⇄ Form): incident-type tiles from scenario pack (optional quick-start chips), pin, people count, vulnerable checkboxes; switching keeps entered data | C | DONE | T-008, T-018 | Form path and chat path for the same case produce byte-identical `Request` JSON (excluding ids/timestamps); contract test Design: `docs/design/public-02-report.png` |
| T-039 | **Confirmation card before submit** (shared component for chat + form): shows what we understood, editable fields, "Send now"; nothing is submitted without tap; status page per `public-04-status.png` | C | DONE | T-006 | Cannot submit without confirm tap (e2e test); card renders in en/hi Design: `docs/design/public-03-confirm.png`, `docs/design/public-04-status.png` |

## Day 4 / Fri 16 Oct — Scenarios, stability, video
| ID | Task | Owner | Status | Depends | Acceptance criteria |
|---|---|---|---|---|---|
| T-040 | **Flood main scenario** seeded end-to-end (≈45 reports incl. duplicates, update, hoax, silent zone) in DEMO_MODE with cached Gemini responses | C | DONE | T-036 | Demo script (BUILD_BRIEF 13) runs top to bottom in <2:45 without live Gemini |
| T-041 | **Dog-attack scenario pack** = `data/scenarios/dog_attack.yaml` + synthetic seeds ONLY (no new screens/code branches), fixed first-aid string from `dog-attack-scenario.md`, scenario switcher toggle | A | DONE | T-040, T-018 | Switcher flips to dog pack in both apps; no LLM-generated medical text anywhere |
| T-045 | **Safety lines**: single reviewed `safety_lines` file (en/hi/hinglish/ta) used by chat agent and UI; test that agent output never contains advice outside those ids; 112 banner on every public screen | C | DONE | T-019, T-018 | Red-team prompts ("what medicine?", "is it safe to swim?") return only fixed lines or "call 112" Design: `docs/design/public-01-home.png` |
| T-042 | Stability checklist (BUILD_BRIEF 11.2): min-instances, budget alerts, rate limits, kill-switch test, uptime check, Firestore rules test | U + C | TODO | T-036 | Checklist ticked in WORKDONE with evidence |
| T-043 | Accessibility + i18n QA: Hindi/Tamil/Hinglish passes on both layouts, contrast, text overflow, 112 banner translated | C | DONE | T-007, T-040 | Screenshots of each language attached to WORKDONE Design: `docs/design/public-06-report-hi.png`, `docs/design/coordinator-command-hi.png` |
| T-054 | **Demo-mode phone frame**: when `?demo=1` (or toggle in coordinator top bar) on desktop, show the public routes inside a phone-shaped frame (≈390x844) beside the coordinator view, so both can be shown side by side for the video; hidden on real phones | C | DONE | T-046, T-040 | Side-by-side layout at 1920x1080 is recordable; submitting a report in the frame appears in the coordinator queue live; no frame on viewports <600 px | Design: `docs/design/public-contact-sheet.png`, `docs/design/coordinator-command.png` |
| T-044 | Record video v1 (<3:00, 1080p, captions) from deployed app + local backup recording | U | TODO | T-040 | Plays logged-out |
| S-001 | STRETCH Hourly news-search agent for area alerts (Gemini + search grounding, Cloud Scheduler → Pub/Sub → alert; shown in Alerts view; flagged as unverified, human dismisses) | A | TODO | T-031, T-037 (freeze exception approved by U) | Hourly job produces ≥1 alert on seeded/mock news feed; clearly labelled "unverified news signal" |
| S-002 | STRETCH 1,000-message surge test | C | TODO | T-042 | Drain time and error counts recorded |
| S-003 | STRETCH Volunteer "offer help" flow | A | TODO | T-037 | Offer requires coordinator approval |

## Day 5 / Sat 17 Oct — Submit (target)
| ID | Task | Owner | Status | Depends | Acceptance criteria |
|---|---|---|---|---|---|
| T-050 | Replace deck placeholders with real numbers + screenshots (`coordinator-*.png`, live) ; export PDF ≤ 5 MB | U (+ Grok Bot) | TODO | T-032, T-044 | Numbers match `bench/results` file |
| T-051 | README (live URL, run locally, safety, limitations, synthetic statement) + **demo section with seeded coordinator credentials (synthetic, from T-047)** | C | TODO | T-036 | Fresh clone follows README successfully |
| T-052 | Repo hygiene: gitleaks on full history, grep for other project names, LICENSE, tag `v1.0-submission` | U | TODO | T-051 | Scans clean; deployed revision = tag |
| T-053 | Final video upload, description ≤1,024 chars, theme dropdown, submit on portal; save confirmation | U | TODO | T-050, T-052 | Confirmation saved in WORKDONE |
| – | 18 Oct: buffer only (deadline 11:59 PM IST) | U | – | – | – |

## First-pass reliability (branch cursor/first-pass-e2e-70f2 → ux-uplift)
| ID | Task | Owner | Status | Depends | Acceptance criteria |
|---|---|---|---|---|---|
| FP-01 | Offline report queue stores, retries, and dedupes | C | DONE | T-028 | Phone queue survives offline send; retry uses one idempotency key; server returns the same request |
| FP-02 | Live coordinator queue | C | DONE | FP-01 | New public report appears within 5 s without reload |
| FP-03 | Hinglish/Hindi intake place, ward, vulnerable, raw text | C | DONE | FP-01 | Pytest for the three TEST_REPORT examples |
| FP-04 | Triage bands: critical cases are Needs help now | C | DONE | – | At least 3 seeds in Needs help now; chip and banner counts match |
| FP-05 | Rescue matches boat/rescue, not shelter, unless labelled fallback | C | DONE | – | Pytest; benchmark not worse |
| FP-06 | Honest status timeline, local time, short ID | C | DONE | – | Timeline matches real status |
| FP-07 | Chat fully localized | C | DONE | – | No raw keys in chips, prompts, or review |
| FP-08 | Dispatched and Completed lifecycle | C | DONE | FP-05 | Approve leaves the active queue; complete frees capacity |
| FP-09 | Teams view | C | DONE | FP-08 | All resources listed; typed map pins |
| FP-10 | Team location and simulated movement | C | DONE | FP-09 | Manual update; simulated path labelled |
| FP-11 | Filters in the URL and timestamps | C | DONE | FP-02 | Status, type, area, time persist; empty state |
| FP-12 | Time-based priority rise | C | DONE | FP-04 | Injected clock raises the score; reason chip |
| FP-13 | Kerala case study | C | DONE | – | Districts Alappuzha, Ernakulam, Thrissur, Wayanad; synthetic people; Riverbend and Lucknow removed from app data |
| FP-GAP | No team free, confirm link, seed clock | C | DONE | FP-12 | Estimated wait, resource gap alert, team confirm page, last-hour seeds |
| FP-14 | Demo coordinator button on login | C | DONE | – | One click from /coordinator/login in demo mode |
| FP-15 | Alerts map polish | C | DONE | – | Ward outlines, numbered typed pins, silent zone |
| FP-16 | Accuracy report naming | C | TODO | – | Plain metric names vs first-come-first-served |
| FP-17 | Mobile coordinator layout | C | TODO | FP-08 | No horizontal overflow at 390; case detail sheet |
| FP-18 | i18n of case content | C | TODO | FP-13 | Translations field shown for the selected language |
| FP-19 | Small fixes: 112 text, chhat, sass @use, reset demo | C | TODO | – | Documented build and reset |

## T-UX-03 UX3 uplift (branch ux-uplift)
- DONE: tokens + light/dark/system theme (shared ThemeService), CallPill, QuietFooter, settings sheet, landing, coordinator login
- TODO/BLOCKED (not started): public layout + tab bar, report chat + voice overlay, confirm, status, nearby, coordinator dashboard + tour, alerts, accuracy report, states
- T-UI-01 and UX2 tasks superseded by T-UX-03
- [x] T-UX-03 coordinator dashboard (briefing, sticky approve bar, tour, theme/language menu, shared band counts), public layout + tab bar, report chat, review, status, nearby, alerts, accuracy report, DEMO_MODE-gated demo entry. Unit tests: web 40 + shared 8 green. Not done: undo-after-approve toast (no un-approve API), photo attach in composer, separate public Home tab screen (landing is home), coordinator detail slide-over close control below 1280px.
- [x] P0 public entry: Home screen, My requests, Find my request, 4-tab bar on all public pages, request ID copy/share on status.
- [x] Alerts map overhaul (ward outlines, typed numbered pins, zoom/dim, key); home coordinator button; i18n template lint.
