# Relief Desk: GCP & Firebase Setup, Budget Alerts & Key Restrictions

## 1. Budget Alerts Setup (Google Cloud Console)
1. Go to **Google Cloud Console > Billing > Budgets & alerts**.
2. Create budget:
   - Target amount: Set monthly threshold (e.g. $25 - $50 USD for hackathon evaluation period).
   - Alert thresholds:
     - 50% of budget: Notification email to responders (`team-lead@reliefdesk.internal`).
     - 80% of budget: Notification email + automated notification hook.
     - 100% of budget: Notification email; trigger automated kill-switch (`GEMINI_ENABLED=false`).
3. Verify receipt of budget test alert.

## 2. Google Maps Platform Key Restrictions
1. Go to **APIs & Services > Credentials > API Keys**.
2. Select `Relief Desk Maps Key`.
3. Set **Application Restrictions**:
   - HTTP referrers (web sites)
   - Allowed referrers:
     - `http://localhost:*/*`
     - `http://127.0.0.1:*/*`
     - `https://relief-desk-*.web.app/*`
     - `https://relief-desk-*.firebaseapp.com/*`
4. Set **API Restrictions**:
   - Restrict key to only "Maps JavaScript API".
5. Test:
   - Calling Maps JS API with an allowed referrer succeeds.
   - Calling Maps JS API with an unauthorized referrer returns `403 RefererNotAllowedMapError`.

## 3. Gemini / Vertex AI Key Hygiene
- Never commit keys to git repository.
- Secrets stored in Google Secret Manager or local git-ignored `services/api/.env`.
- Per-user rate limits and daily spend caps enforced in `services/api/app/config.py`.
- Global kill-switch: `GEMINI_ENABLED=false` immediately falls back to deterministic/cached demo responses.
