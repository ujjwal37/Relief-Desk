# Relief Desk: final demo flow (single source of truth)

Priority: a first-time judge is never confused; every screen has one obvious next step. Trimmed scope agreed 17 Oct 2026, 23:48 IST. FROZEN 18 Oct 2026, 00:02 IST: no further spec changes.

Status legend: DONE (on main 2afee28) · PARTLY (built in a worktree, not reviewed/pushed) · TO BUILD. Estimates are focused engineering time including tests.

## A. Reporter (phone)

### A1. One-shot report: guided chips + one text box + mic. TO BUILD (~3 h)
- Behaviour: language row EN / हिंदी / മലയാളം / Manglish; each has 4 chips (stranded family, someone not breathing, reworded repeat, suspicious/hoax, plus "relative reporting from elsewhere" for the mismatch demo). A chip PREFILLS the editable box, never sends. One input row: text box + existing mic. One Send = one complete report through the normal AI pipeline. No automatic follow-up questions (old loop kept behind REPORTER_FOLLOWUPS=false).
- Edge cases: voice transcript goes through the same gate (A3); empty Send disabled; double-tap Send is idempotent (idempotency key).
- Today: the chat flow sends raw_text = first message and structured facts from follow-up answers. This is the RD-9914 root cause (A6).

### A2-lite. One optional "Share location" button — TO BUILD (~2 h)
- One optional GPS button, shown beside Send and again on the receipt. Never a gate, never blocks Send (3 s timeout). Permission is asked only at the tap, with a reason line + "Used only for this rescue request".
- Case shows "Reporter GPS ±N m"; >200 m or a fix older than 10 min shows "approximate" and is never used as exact for routing.
- The typed landmark is always kept and shown with the pin. Text landmarks are matched only against the Kuttanad list (High/Medium); no match = text, no pin. No IP geolocation.
- Demo panel only: a preset Kuttanad point labelled "Demo location" on phone and case; never on the real path.
- CUT: Places search, "For me / Someone else" chips, location-mismatch flag.

### A3. Greeting / gibberish gate. TO BUILD (~1.5 h)
- hi, hello, ok, namaste, ഹായ്, test, blank → one line "Tell me what's happening and where" in the reporter's language/script, no case. Gibberish/off-topic → "I couldn't understand — describe the emergency and place", no case.
- Life-threat words bypass the gate even when the message is short.

### A4. Receipt in the reporter's language. TO BUILD (~2 h)
- "Received RD-xxxx. I understood: 2 people, water rising, near St. Mary's, Kainakary. Place: not stated." Built from the extracted record, not an echo of the input. Gemini failed/timeout/non-JSON → "Received RD-xxxx, a coordinator will read it." "Reading this report…" always clears (done or failed).
- "Share location" one-tap chip on the receipt when place is missing; updates the SAME case.

### A5. Offline queue. PARTLY (offline save exists; ~1 h)
- Failed send: text stays, "Queued, will send when network returns", auto-retry on `online`, idempotent so no duplicate case. No SMS/WhatsApp.

### A6. No invented fields (RD-9914 fixes). TO BUILD (~2 h)
- Root cause (read-only on served): raw_text "hi"; people 4 / disabled / "im located in allepy" came from chat follow-up answers sent as structured facts; Gemini only saw "hi". Empty place_text rendered the literal i18n "Place" in the step headline (step-detail-dialog headline()).
- Fixes: one-shot text; the server ignores client people/place without a quoted span; missing = "not stated"; never render placeholder tokens; no location → no "~? min" options, only "Call reporter" (phone on file) / Escalate; non-JSON Gemini → desk card "Unparsed, needs a human" with the raw text, labelled rules fallback, never a guessed case. Regression test for each.

### A7. Photo with the same Send — TO BUILD (~3 h)
- Today: the reporter's photo widget accepts JPEG/PNG/WebP up to 2 MB, requires a "synthetic demo image" tick, shrinks to 768 px in the browser and calls a separate rate-limited /api/intake/photo for short-lived observations. /api/reports also accepts image_base64 (server shrinks it, Gemini reads it with the text), but the image is not kept on the case.
- Frozen: the photo goes with the same ONE Send, with or without text. Compressed in the browser to max ~1280 px / under 500 KB, and included in the offline queue.
- Gemini reads image + text. The receipt mentions only what is visible ("photo shows water at waist level"), never invented.
- Photo only: fine, creates a case if Gemini sees an emergency. Unrelated photo (selfie/meme) with no text → "I couldn't understand" reply, no case.
- The photo is shown on the case for the coordinator; facts from it are labelled "from photo".
- Tests: photo + text, photo only, large photo (compression), unrelated photo, offline + photo.

## B. Coordinator (desk)

### B1. Life-threat → 112 lane. DONE (verify with missing place/count: ~0.5 h)
- Matched words shown + Call 112, even when place/count are missing.

### B2. Duplicate flag + Merge / Keep separate. DONE (2afee28)
- Never auto-merged (submit-time dedupe and "now N people" updates both flag). Signals: GPS ≤300 m, same landmark + ward, gist; 24 h window. Card: "Possible duplicate of RD-xxxx", High/Medium, reasons, differences ("3 vs 4 people → plan for 4"). Rated from merged facts; a flagged report never scores below its match. Approve is disabled on a flagged case until Merge/Keep; merge logs who decided.
- Not done: the phone-number signal (no stored phone field, never claimed). Merge P/R measured rules-only: P 0.548 / R 0.102 on flood_v1 (no GPS in that set). Not shown on Accuracy.
- Duplicate arriving mid-approval: the new report is flagged against the case; the frozen dispatch is not re-matched.

### B3. Frozen dispatch at Approve. DONE
- Team, seats and ETA frozen at the click; later reports never change the dispatched numbers.

### B4. Ask reporter loop — CUT
- Any existing "Ask reporter" label/button is hidden so there is no dead end. Missing fields show "not stated".

### B5. Tour (5 steps, non-blocking). PARTLY (agy worktree, under review; ~1.5 h)
- Corner card "Take a 60-second tour · Start / Skip", no modal/dimming/auto-advance. Steps: lane, Gemini trace, team + Approve, possible duplicate, reporter phone button. Skips missing anchors, no numbers not on screen. Never re-shown after Skip/finish; replay from header "Tour" (removed from Demo tools).

### B6. Phone side panel. PARTLY (agy worktree; ~2 h after A1)
- Header "Try as a citizen" opens a docked 390 px frame; queue/map reflow; QR + new-tab link; "Your report · RD-xxxx" chip jumps without changing the selection; mic allowed in the frame.

### B7. DEMO_TOOLS flag. PARTLY (both worktrees; ~0.5 h)
- Demo tools menu hidden unless DEMO_TOOLS=true; off on the judging build.

### B8. Removals and data sweep. PARTLY (track C worktree; ~2 h review/finish)
- Remove "Received 0/8" counters, "Search beyond 15 km · 547 min", unexplained RD·km on Teams rows, sparkles, Alerts badge mismatch. Fix Thottappally description, "Mata Mandir", RD-2135 church/market, "bridge bridge", stale 91 km raft main button (prefer Escalate). Reporter summary not concatenated; Manglish follow-up language; Explained score = final score; one step count.

## C. Failure modes (cross-cutting)
- Gemini quota/429: pause for the retry delay, rules fallback, label "Gemini unavailable, built-in rules". Timeout 45 s: rules result final; a late reply only becomes a re-check diff. Non-JSON: "Unparsed, needs a human".
- Network drop: phone queue (A5); desk live feed reconnects.
- Messy-input gate (release gate): hi, ok, blank, ഹായ്, namaste, test, gibberish, off-topic, "help", place-only, count-only, Manglish typos, mixed ML+EN, voice run-on, Hindi, Malayalam not-breathing, full English, reworded repeat. Must pass on fallback; on Gemini if quota allows.

## D. Demo script (~3 min)
1. Welcome page: "Floods bury coordinators in messy multilingual messages; Relief Desk turns them into ranked, deduplicated, dispatchable cases with a person approving every dispatch."
2. Coordinator → "Enter as demo coordinator" → tour card appears → Skip → queue with the life-threat lane on top, map with pins.
3. "Try as a citizen" → side panel. Tap Manglish chip: `Kainakary jettyde aduthu veettil vellam kayari, 3 per und, oru ammachi nadakkan pattilla` → edit "3" if wanted → Send → receipt "Received RD-xxxx. I understood: 3 people, elderly can't walk, near Kainakary jetty." → queue chip "Your report · RD-xxxx" → click → open the Gemini trace.
   RISK: Gemini latency/quota. Fallback: the receipt says "a coordinator will read it" and the trace shows the rules label honestly; narrate it.
4. Malayalam chip: `ശ്വാസം കിട്ടുന്നില്ല, കൈനകരി പള്ളിയുടെ അടുത്ത്, പെട്ടെന്ന് വരണം` → Send → 112 card with the matched words, case at the top of the lane.
5. English chip: `Four people stuck near Kainakary boat jetty, water rising, elderly woman cannot walk` → Send → "Possible duplicate of RD-xxxx · High · 3 vs 4 people → plan for 4" → Merge.
   RISK: highest. Whether it reads High or Medium depends on the GPS/landmark match. Fallback: the demo-location pin is fixed; if it reads Medium, say so and Merge anyway.
6. Select the merged case → Approve the suggested nearest free boat → dispatched card shows frozen team, seats, ETA.
   RISK: no free boat near. Fallback: Escalate is the main button; narrate.
7. Hoax chip: `NASA says the dam will burst in 10 minutes, everyone evacuate, forward this` → Send → hoax chip, held for review, low score.
8. Situation: waiting / dispatched / free boats / free medical counts match the queue.

## E. Judge patches (frozen)
- A "Place: not stated" case shows a static next step: "Location needed: wait for the reporter to share location, or escalate" (a tel: link only if a reporter phone exists; none is stored today). No dead end.
- Welcome "I need help" opens the citizen phone directly: no login, no blank page.
- The tour card never covers the phone panel.
- No periodic reset/reseed timer exists (verified: reset and full-scenario load only run from confirmed clicks in Demo tools, which are off on the judging build). Judge actions are never wiped.
- Final-build gate: the receipt rephrases (no echo/stitching), stays in the reporter's language and script, says "not stated" for missing details, and arrives in under ~8 s on Gemini (p50/p95 measured). Re-run the duplicate 4-step (Manglish → English reword with 4 → Malayalam script → other-side-of-canal negative) and the life-threat set (not breathing, oxygen, labour) on Gemini. Free tier only; any fallback labelled.
