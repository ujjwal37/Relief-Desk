# docs/design — UI references

All screens belong to ONE Angular + Ionic + Capacitor PWA (`apps/web`): `public-*` mockups are the public routes (mobile-first `PublicLayout`, no login), `coordinator-*` mockups are routes under `/coordinator` (desktop-first `CoordinatorLayout`, Firebase Auth). The landing screen at `/` (two choices: I need help / report, I'm a coordinator) and the coordinator login screen have no mockup yet: build them in the same visual style (T-046, T-047). Demo-mode phone frame shows public routes inside a phone shape beside coordinator view (T-054).

Build the UI to match these mockups (layout, hierarchy, flows). Mockups are static; maps are drawn placeholders for Google Maps. Only English and Hindi are translated in the mockups; all four languages (en, hi, hinglish, ta) are required in the app.

| File | Screen | Tasks (TASKS.md) |
|---|---|---|
| public-01-home.png | Public Home: one big Report button, Call 112, no sign-up (also base for landing `/`) | T-046, T-029, T-045 |
| public-02-report.png | Report screen, chat-first, voice/text, Chat/Form toggle, location pin | T-008, T-019, T-038, T-028, T-034 |
| public-06-report-hi.png | Same Report screen in Hindi (i18n reference) | T-007, T-043 |
| public-03-confirm.png | Confirmation card ("what we understood", edit, Send now) | T-039, T-008 |
| public-04-status.png | Status: received > matched > help on the way | T-039, T-030 |
| public-05-nearby.png | Nearby incidents map (area-level only) | T-030 |
| public-contact-sheet.png | All public screens overview; reference for phone frame | T-006, T-029, T-054 |
| coordinator-command.png / .html | Coordinator command view (dark): ranked queue, map, why-match panel, Approve (`/coordinator`) | T-047 (login, no mockup), T-054, T-023, T-024, T-025, T-026, T-027, T-013 |
| coordinator-command-light.png / .html | Light theme variant of command view | T-006, T-023 |
| coordinator-command-hi.png / .html | Command view in Hindi | T-007, T-035, T-043 |
| coordinator-alerts.png / .html | Alerts view (spike, silent zone, gaps, news signal) | T-031, S-001 |
| coordinator-benchmark.png / .html | Benchmark view (numbers are PLACEHOLDERS) | T-033, T-032 |

Scenario switcher (flood/dog pack) appears in the coordinator top bar: T-018, T-041.
