"""Record Gemini replies for the seeded Kerala flood reports.

Usage (from the repo root, with a real key):
    GEMINI_API_KEY=... make record-ai

Exits without writing when the key is missing, replace-me, or
synthetic-demo-gemini-key. Does not store deterministic fallback text.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.llm.record import record_seeded_reports  # noqa: E402


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--traces',
        nargs='*',
        help='Record complete pipeline traces. With no ids, every demo seed case is run once through Gemini.',
    )
    args = parser.parse_args()
    if args.traces is not None:
        from app.llm.record import record_seeded_traces
        if not record_seeded_traces(args.traces):
            raise SystemExit('No complete Gemini traces recorded; fallback provenance was preserved.')
    else:
        record_seeded_reports()


if __name__ == "__main__":
    main()
