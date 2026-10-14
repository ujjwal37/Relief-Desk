# UI-REF-03 — Agent workspace

Removed the duplicate suggestion chips below the chat composer on the Agent page. The three starter questions remain in the welcome view. The embedded Ask the desk variant retains its existing shortcuts.

The page now has a wider pine-and-sand workspace, a visible title and purpose, an introduction beside the starter questions, and a composer anchored below the conversation. Mobile shows concise starter questions and keeps the composer accessible. Existing component class logic and API/service behavior are unchanged.

## Verification

- Development build and i18n checks passed.
- Five Playwright combinations passed: desktop/mobile light and dark, plus mobile Hindi. Checked three starter cards, no duplicate chips, no horizontal overflow or raw labels, and the reply/composer state after selecting a starter. Chat replies used a synthetic intercepted response, with no live model calls.
- All four AskDeskComponent unit tests passed, including updated assertions that duplicate suggestions stay absent before and after an answer. Tests used a temporary TypeScript config containing only this spec. The normal workspace test compilation is blocked by the pre-existing incomplete Teams count expectation in `coordinator-command.component.spec.ts:248` (missing `busy` and `notUpdated` fields).
- Source comparison confirms both edited component classes are unchanged; edits are in their templates/styles. `git diff --check` passed.

## Screenshots

- [Desktop](agent-desktop.png)
- [Mobile](agent-mobile.png)
- [Dark mode](agent-dark.png)
