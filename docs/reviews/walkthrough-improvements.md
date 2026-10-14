# Suggested improvement coverage

Source: the user-provided walkthrough recommendations. Its proposed implementation details were evaluated against the existing project and its safety rules.

| Suggestion | Result |
|---|---|
| Broken landing `/report-preview` | Landing opens `/report` in the same tab on desktop/mobile. Preview route remains available for existing links. |
| Model timeouts / ADK | Live language calls execute through ADK with the existing quota, queue, cache, circuit breaker and HTTP timeout. Default timeout 20s; network/validation repairs share at most two retries. Duplicate and urgency language reviews run concurrently. Python sets every score and match. |
| Force Gemini 2.5 Flash | Actual account returned 404 for 2.5 Flash. 3.8 Flash returned high demand (503); configured 3.5 Flash Lite succeeded. Model remains configurable. No latency guarantee or benchmark claim was added. |
| Genuine seed traces | INC-001 and INC-008 have authentic recorded intake and three language reviews, including model, latency and tokens. Matching is labelled Python tool. Replay verifies the case-input fingerprint and uses Recorded (Gemini) labels. |
| Deliberate fallback toggle | Drawer-local Preview rules fallback checkbox. No persisted provenance or dispatch decision changes. |
| Duplicate/truncated urgency text | Complete reason wraps, with one prefix. Tool/cache/fallback sources are distinguished; intentional tools no longer produce a timeout warning. |
| Random title text | No typo in seed files. Old phone tests generated the `kfer…` suffix; changed to readable Demo IDs and Kainakary Ferry Jetty. No report was automatically deleted. |
| 68 km oxygen match | Corrected Varapuzha clinic coordinates. INC-008 now matches at 1.65 km / calculated ~5 min. No fictional hard-coded ETA. |
| Map lines and labels | One recommended line by default; inspecting another team shows its line. Dark pill, no text outline, hover reset fixed. |
| Map loading | Shared shimmer, tilesloaded readiness, bounded config/script loads, existing schematic fallback and reduced-motion support. |
| Consistent palette | Existing shared coordinator shell/tokens retained across views. New controls use those tokens. |
| Live surge | Authenticated, DEMO_MODE-only, five synthetic reports two seconds apart through normal intake/SSE. Single-run guard, cooldown, progress/poll fallback, actual merge notice, fresh-arrival spike alerts and overview count. No forced merge or score of 92. |
| Rabies/RIG narrative | Existing scenario menu loads the dog pack and its YAML facilities. DOG-001 is a synthetic human-entered clinician referral; stock requirements are not inferred by AI. Python excludes unstocked facilities, rechecks/allocates stock atomically on approval and prevents double allocation on retry. No treatment or dose advice. |
| Multimodal photo | Explicit synthetic-photo analysis, real image bytes through guarded Gemini/ADK, size/type/dimension validation and metadata stripping. Schema-limited water/damage observations are unverified. Reporter must review before adding details to the draft and still confirm submission. Images are not stored; text/offline submission remains intact. No “AI Vision Verified” claim. |
| Status closure | Existing approve → arrived → completed API and private reporter SSE retained and tested. Fixed immediate browser team-free state and zero-capacity free markers. Supplies are not replenished when team seats are released. |
| Presentation screenshots | Four requested screenshots plus mobile/report/surge/inventory/fallback QA images captured and visually reviewed. See the screenshot index. |

## Verification

- Full FastAPI regression suite: 283 passed, 1 optional live smoke skipped.
- Angular application: 132 tests passed; shared library: 8 tests passed.
- Browser: five walkthrough/live-update tests passed on actual rendered pages, including private status updates without reload, stock scenario, synthetic surge, photo outage and responsive entry.
- Production build passes, with the existing coordinator stylesheet warning (27.36 kB vs 20 kB warning budget; below its 30 kB error budget).
- All four translation catalogs pass parity and template checks.
- Real Gemini text and image calls were verified separately; recorded traces were produced by the recorder, never fabricated.

## Runtime notes

New backend code requires an API restart. The existing server on port 8000 was left running to preserve its in-memory synthetic cases. To see demo-only surge/scenario controls, use DEMO_MODE=true; this does not disable a real Gemini key. The Angular dev server watches frontend changes automatically.

The deployed service and presentation deck were not changed. Routing and ranking remain decision support; every dispatch still requires a coordinator.
