# Recorded Gemini replies

This directory has no Gemini transcripts until someone runs `make record-ai` with a real `GEMINI_API_KEY`.

The command calls the configured model for each seeded Kerala flood report and writes `data/ai_cache/{prompt-hash}.json`. It exits before writing when the key is missing, `replace-me`, or `synthetic-demo-gemini-key`. A fallback reply is not stored and is not badged as a recorded run.

`AI_MODE=replay` serves a file from this directory. The case badge is "Recorded Gemini run". A report whose prompt is not in this directory still calls Gemini when a real key is set.
