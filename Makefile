.PHONY: bench record-ai

PYTHON ?= python3

# Rule baseline versus Gemini. Gemini stays unmeasured when GEMINI_API_KEY is unset.
bench:
	$(PYTHON) bench/run_bench.py --dataset data/synthetic/flood_v1 --split test --seed 42 --out bench/results

# Calls Gemini and writes data/ai_cache. Exits with no files when the key is a placeholder.
record-ai:
	$(PYTHON) scripts/record_ai.py

# One real Gemini pass over the demo seed cases. Writes data/ai_cache/*.trace.json.
# Needs GEMINI_API_KEY. Does not invent replies when the key is missing.
record-traces:
	$(PYTHON) scripts/record_ai.py --traces
