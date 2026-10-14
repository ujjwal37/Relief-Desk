# UI-REF-01 — Reference UI alignment

Reference: `/home/sr/Downloads/relief-desk-ui-redesign` (provided by the user).

## Visual audit and changes

The reference uses warm off-white backgrounds, pine primary actions, muted green selections, 12 px cards, 16 px map corners, and a 64 px header. Its desktop layout has a 352 px case queue, a centered map, and a 400 px decision panel. The previous UI used zinc neutrals, an inset three-column layout, truncated queue titles, and a map stretched to fill the screen.

The UI now uses the reference's light palette and panel structure. Queue cards show two-line titles, priority and severity separately, and existing case metadata. The decision panel groups the existing explanation, team match, and original report into distinct cards. Approval and team selection share a row. Secondary coordinator screens, public screens, and login use the same surfaces, spacing, corners, and pine primary actions. Emergency call controls retain the red emergency treatment. Dark mode uses the existing dark surfaces with a coordinated pine accent.

The reference's sample forecasts, assets, and static case data were not copied into the app. All displayed values come from existing app state. Existing event handlers, routing, API/service code, data, configuration, scoring, and dispatch logic are unchanged.

## Verification

- `npx ng build web --configuration=development` passed.
- `node scripts/check-i18n.mjs` passed for all four catalogs.
- `git diff --check` passed.
- Playwright screenshots and browser checks covered 23 page/viewport/theme/language combinations. The saved [browser check results](checks.json) show no horizontal overflow, raw translation keys, or page exceptions.
- Additional checks at widths 1024, 1366, and 1920 passed. The mobile form/confirmation view at 390 px passed.
- Reviewed English and Hindi, light and dark modes, and desktop/mobile layouts. All new labels render as text; `uiRef.areaIntelligence` renders as “Area intelligence”.
- A source comparison confirmed that TypeScript edits are confined to inline styles and that existing template event bindings are unchanged.
- Visual verification used the running local app. No reports or dispatch approvals were submitted, and the full intake/dispatch test suites were not run for this presentation change.

## Reviewed screenshots

- [Dashboard](dashboard.png)
- [Dashboard Dark](dashboard-dark.png)
- [Dashboard Mobile](dashboard-mobile.png)
- [Overview](overview.png)
- [Teams](teams.png)
- [Accuracy](accuracy.png)
- [Agent](agent.png)
- [Landing](landing.png)
- [Login](login.png)
- [Public Home](public-home.png)
- [Public Report](public-report.png)
- [Confirmation](confirmation.png)
- [Dashboard Hindi](dashboard-hindi.png)
