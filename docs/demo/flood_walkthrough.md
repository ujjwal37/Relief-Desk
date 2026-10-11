# Flood demo walkthrough (BUILD_BRIEF section 13)

Run the timed path with cached responses, no live Gemini:

```text
python scripts/demo_run.py
```

The command sets `DEMO_MODE=true` and `GEMINI_ENABLED=false` before the API loads, seeds at least 45 synthetic Riverbend reports (duplicates, the "ab 5 log hain" update, a hoax that is flagged and kept, and Ward 12 as a silent zone), then walks the beats below. It must finish in under 2:45.

| Time | Show | Line |
|---|---|---|
| 0:00 | Title. Kerala 2018, about 25% duplicate reports (cited in BUILD_BRIEF). | Too many noisy reports, not too few. |
| 0:15 | Phone: Hindi voice transcript, then Hinglish text, then the confirmation card. Nothing is sent until Send now. | Reports in the way people actually talk. |
| 0:40 | Coordinator queue and map. Original message beside the AI reading. | We keep the original and show confidence. |
| 1:05 | Duplicate evidence on the Ram Ghat cluster. The update raises the people count. Split/undo is a human action. | Duplicates merge, updates escalate, humans can undo. |
| 1:30 | Child and elderly case at the top of the ranked queue, with the reason string. Weights are the slider. | Vulnerable cases surface first, with a reason. |
| 1:55 | Why-this-match scores. Approve. Capacity changes only after that tap. Phone status updates. | A human approves every dispatch. |
| 2:15 | Hoax row still in the list. Public nearby map is area cells only. | Flagged, not deleted. Public sees areas, not people. |
| 2:35 | Numbers from `bench/results/latest.json`. Call 112. | Measured on synthetic data; decision support, not dispatch. |

Presenter login, if the coordinator screen asks: `demo-coordinator@reliefdesk.internal` / `KeralaRelief2026!`.
