# Recorded Gemini replies

`fixture.json` lists the demo seed and the scripted phone reports. Every `response` is null until someone runs `make record-ai` with a real `GEMINI_API_KEY` and quota. That command writes `data/ai_cache/{prompt-hash}.json`. It exits before writing when the key is missing, `replace-me`, or `synthetic-demo-gemini-key`. A fallback reply is not stored.

`AI_MODE=replay` serves a hash file and the trace says Recorded (Gemini). A catalog prompt that is still empty uses the deterministic fallback and does not call Gemini. A report that is not in the catalog can still call Gemini when a real key is set.
