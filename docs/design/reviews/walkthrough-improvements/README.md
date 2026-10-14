# Walkthrough improvements — verified screenshots

Captured from the local application with Playwright on 14 October 2026 IST. All people and reports are synthetic. Maps in these reproducible screenshots use the built-in schematic provider; no Google tiles were substituted or edited. Gemini labels come from real recordings, not mocked browser responses.

| Screenshot | Size | Shows |
|---|---|---|
| [coordinator-command.png](coordinator-command.png) | 1366 × 768 | INC-008, Varapuzha clinic 1.65 km away, calculated ~5 min ETA, one readable distance pill, human approval |
| [1366-how-it-decided.png](1366-how-it-decided.png) | 1920 × 1080 | Four genuine recorded Gemini language reviews, Python matching, complete urgency reason, no false timeout banner |
| [phone-desk-merged.png](phone-desk-merged.png) | 1366 × 768 | Clean seeded merged case and shared coordinator palette; the seed genuinely contains 3 reports |
| [coordinator-hindi.png](coordinator-hindi.png) | 1366 × 768 | Hindi coordinator with nearby match |
| [coordinator-mobile-hi.png](coordinator-mobile-hi.png) | 390 × 844 | Hindi mobile coordinator, compact header, no horizontal overflow |
| [report-1366.png](report-1366.png), [report-390.png](report-390.png) | 1366 × 768 / 390 × 844 | Direct landing-to-report navigation and photo attachment control |
| [live-surge.png](live-surge.png) | 1366 × 900 | Five synthetic arrivals through normal intake; actual update/merge outcomes |
| [referral-stock.png](referral-stock.png) | 1366 × 900 | YAML clinician-referral requirement, 3 RIG stock units, farther stocked facility selected over nearer unstocked clinic |
| [photo-offline-fallback.png](photo-offline-fallback.png) | 390 × 844 | Explicit synthetic-photo analysis, unavailable-state messaging, text reporting remains available |

Regenerate with:

```sh
CHROME_BIN=/usr/bin/chromium npx playwright test e2e/walkthrough-improvements.spec.ts e2e/live-updates.spec.ts --reporter=list
```

The tests start isolated servers on 8100/4300 with DEMO_MODE=true, placeholder keys and AI_MODE=fallback. Seeded recordings remain honestly labelled Recorded (Gemini). Fresh test reports use rules, so tests do not spend quota. Live Gemini text and image transport were separately verified on the configured gemini-3.5-flash-lite account.
