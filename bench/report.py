import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "bench" / "results"


def generate_report(results_json_path: Path):
    if not results_json_path.exists():
        print(f"Error: {results_json_path} does not exist. Run run_bench.py first.")
        sys.exit(1)

    with open(results_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    m = data.get("metrics", {})
    failures = data.get("failure_examples", [])

    md_path = RESULTS_DIR / "latest.md"
    csv_path = RESULTS_DIR / "latest.csv"

    # Render Markdown table
    md_lines = [
        "# Relief Desk Benchmark Results (BUILD_BRIEF.md Section 9.3)\n",
        f"- **Dataset**: `{data.get('dataset')}`",
        f"- **Split**: {data.get('split_desc')}",
        f"- **Seed**: {data.get('seed')}",
        f"- **Generated At**: {data.get('created_at')}",
        "- **Note**: Evaluated on synthetic dataset\n",
        "## Comparative Metrics Table\n",
        "| Metric | Relief Desk | Baseline | Target |",
        "|---|---|---|---|",
    ]

    for k, v in m.items():
        label = k.replace("_pct", " (%)").replace("_ms", " (ms)").replace("_", " ").title()
        rd_val = v.get("relief_desk")
        base_val = v.get("baseline_keyword") or v.get("baseline_hash") or v.get("baseline_fcfs") or v.get("baseline") or "N/A"
        target_val = v.get("target")
        md_lines.append(f"| **{label}** | **{rd_val}** | {base_val} | {target_val} |")

    md_lines.append("\n## Failure Analysis Examples\n")
    for i, f in enumerate(failures, 1):
        md_lines.append(f"### Failure Case {i}: {f.get('category')} ({f.get('message_id')})")
        md_lines.append(f"- **Message**: \"{f.get('raw_text')}\"")
        md_lines.append(f"- **Ground Truth**: `{f.get('ground_truth')}`")
        md_lines.append(f"- **Relief Desk**: `{f.get('relief_desk')}`")
        md_lines.append(f"- **Analysis**: {f.get('reason')}\n")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    # Render CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Relief Desk", "Baseline", "Target"])
        for k, v in m.items():
            base_val = v.get("baseline_keyword") or v.get("baseline_hash") or v.get("baseline_fcfs") or v.get("baseline") or "N/A"
            writer.writerow([k, v.get("relief_desk"), base_val, v.get("target")])

    print(f"Report generated successfully:\n  - {md_path}\n  - {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render Benchmark Report")
    parser.add_argument("--input", type=str, default=str(RESULTS_DIR / "latest.json"))
    args = parser.parse_args()
    generate_report(Path(args.input))
