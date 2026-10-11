.PHONY: bench

PYTHON ?= python3

# Rule baseline versus Gemini. Gemini stays unmeasured when GEMINI_API_KEY is unset.
bench:
	$(PYTHON) bench/run_bench.py --dataset data/synthetic/flood_v1 --split test --seed 42 --out bench/results
