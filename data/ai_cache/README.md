# Recorded Gemini replies

`fixture.json` lists the demo seed and the scripted phone reports. Every `response` is null until someone runs `make record-ai` with a real `GEMINI_API_KEY` and quota. That command writes `data/ai_cache/{prompt-hash}.json`. It exits before writing when the key is missing, `replace-me`, or `synthetic-demo-gemini-key`. A fallback reply is not stored.

`AI_MODE=replay` serves a hash file and the trace says Recorded (Gemini). A catalog prompt that is still empty uses the deterministic fallback and does not call Gemini. A report that is not in the catalog can still call Gemini when a real key is set.


Two genuine seed runs (INC-001 and INC-008) were recorded on 14 October 2026 using the account's working `gemini-3.5-flash-lite`. Each has a real intake response and a `.trace.json` with four Gemini language turns plus deterministic matching. `python scripts/record_ai.py --traces INC-001 INC-008` regenerates these with the API environment loaded. Invalid or fallback runs do not overwrite recordings. Replay checks the case-input fingerprint and labels model turns **Recorded (Gemini)**; it never labels matching as a model call.
