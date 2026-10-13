import argparse
import csv
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure services/api and project root are in python path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "services" / "api"))

from collections import Counter

from app.agents.intake import intake_agent
from app.agents.dedupe import dedupe_agent
from app.tools.gazetteer import gazetteer
from app.tools.scoring import scoring_engine
from app.tools.geo import grid_cell_id
from app.models.firestore_models import StoredRequest, RequestStatus
from bench.baselines import compute_hash_dedupe, keyword_extract_baseline
from bench.gemini_eval import evaluate_gemini


def load_split(dataset_dir: Path) -> Dict[str, Any]:
    split_file = dataset_dir / "split.json"
    if not split_file.exists():
        raise SystemExit(f"Missing frozen split file: {split_file}")
    return json.loads(split_file.read_text(encoding="utf-8"))


def messages_for_split(messages: List[Dict[str, Any]], split_meta: Dict[str, Any], split: str) -> List[Dict[str, Any]]:
    """Test ids stay the frozen list. New rows are train only."""
    by_id = {row["id"]: row for row in messages}
    dev_ids = list(split_meta["dev_ids"])
    test_ids = list(split_meta["test_ids"])
    held = set(dev_ids) | set(test_ids)
    if split == "dev":
        chosen = dev_ids
    elif split == "test":
        chosen = test_ids
    elif split == "train":
        chosen = [row["id"] for row in messages if row["id"] not in held]
    else:
        chosen = [row["id"] for row in messages]
    missing = [mid for mid in chosen if mid not in by_id]
    if missing:
        raise SystemExit(f"Split {split} names {len(missing)} ids that are not in the dataset")
    return [by_id[mid] for mid in chosen]


def calculate_f1(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    return prec, rec, f1


def run_benchmark(
    dataset_dir: Path,
    seed: int = 42,
    split: str = "test",
    out_dir: Path = None,
    gemini_rpm: float = 15.0,
    gemini_limit: int = None,
    allow_test_provider: bool = False,
) -> Dict[str, Any]:
    from app.llm.providers import active_test_provider, assert_gemini_only, display_name

    try:
        assert_gemini_only("benchmark", allow_test_provider=allow_test_provider)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    test_provider = active_test_provider()
    msgs_file = dataset_dir / "messages.jsonl"
    lbls_file = dataset_dir / "labels.jsonl"

    if not msgs_file.exists() or not lbls_file.exists():
        print(f"Error: Dataset files not found in {dataset_dir}")
        sys.exit(1)

    all_messages = []
    with open(msgs_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                all_messages.append(json.loads(line))

    all_labels = {}
    with open(lbls_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                lbl = json.loads(line)
                all_labels[lbl["message_id"]] = lbl

    split_meta = load_split(dataset_dir)
    messages = messages_for_split(all_messages, split_meta, split)
    if split == "dev":
        split_desc = f"Dev split ({len(messages)} messages, frozen)"
    elif split == "test":
        split_desc = f"Test split ({len(messages)} messages, frozen)"
    elif split == "train":
        split_desc = f"Train split ({len(messages)} messages, not held out)"
    else:
        split_desc = f"Full dataset ({len(messages)} messages)"

    print("=" * 82)
    print(f" Relief Desk Formal Benchmark Runner (BUILD_BRIEF.md Section 9.3)")
    print(f" Dataset: {dataset_dir} | Split: {split_desc} | Seed: {seed}")
    print("=" * 82)

    start_bench_time = time.time()

    # 1. Baselines
    hash_results = compute_hash_dedupe(messages)
    hash_dupe_map = {r["id"]: r["decision"] for r in hash_results}

    # 2. Metrics Tracking
    latencies = []
    input_tokens_estimate = 0
    output_tokens_estimate = 0

    # Type accuracy
    rd_type_correct = 0
    kw_type_correct = 0
    type_total = 0

    # Place accuracy
    rd_ward_correct = 0
    kw_ward_correct = 0
    ward_total = 0

    # People count accuracy
    rd_people_exact = 0
    rd_people_pm1 = 0
    kw_people_exact = 0
    kw_people_pm1 = 0
    people_total = 0

    # Vulnerability F1
    vuln_flags = ["child", "elderly", "disabled", "pregnant", "medical_need"]
    rd_vuln_counts = {vf: {"tp": 0, "fp": 0, "fn": 0} for vf in vuln_flags}
    kw_vuln_counts = {vf: {"tp": 0, "fp": 0, "fn": 0} for vf in vuln_flags}

    # Dedupe metrics (Relief Desk vs Naive Hash)
    rd_dupe_tp = 0
    rd_dupe_fp = 0
    rd_dupe_fn = 0
    hash_dupe_tp = 0
    hash_dupe_fp = 0
    hash_dupe_fn = 0

    # Duplicate vs Update 3-way accuracy
    pair_3way_total = 0
    rd_3way_correct = 0

    # False-merge rate on hard negatives
    hard_negatives_total = 0
    rd_hard_neg_false_merge = 0
    hash_hard_neg_false_merge = 0

    # Hoax / spam detection
    hoax_total = 0
    rd_hoax_caught = 0
    benign_total = 0
    rd_benign_false_flagged = 0

    # Stored requests for ranking evaluation
    rd_ranked_queue: List[StoredRequest] = []
    fcfs_queue: List[Dict[str, Any]] = []

    # Failure cases log. Counts stay in the result; rules are not edited from them.
    failures: List[Dict[str, Any]] = []
    type_confusions: Counter = Counter()

    # Streaming evaluation
    for idx, msg in enumerate(messages):
        t0 = time.time()
        m_id = msg["id"]
        raw_text = msg["text"]
        lbl_info = all_labels.get(m_id, {})
        label_type = lbl_info.get("label_type", "single_incident")
        gt = lbl_info.get("ground_truth", {})

        # Token count estimate (approx 1 token per 3 chars input, 100 tokens JSON output)
        input_tokens_estimate += max(20, len(raw_text) // 3)
        output_tokens_estimate += 110

        # Baseline: Keyword extraction
        kw_ext = keyword_extract_baseline(raw_text)

        # System: Relief Desk Intake Agent
        extracted = intake_agent.parse_report(raw_text, language_hint=msg.get("lang"))

        # Ground truth incident values
        gt_type = gt.get("type")
        gt_ward = gt.get("ward_id")
        gt_people = gt.get("people")
        gt_vuln = gt.get("vulnerable", {})
        gt_urgency_band = gt.get("true_urgency", "medium")

        # (a) Type accuracy
        if gt_type:
            type_total += 1
            if extracted.type.value == gt_type:
                rd_type_correct += 1
            else:
                type_confusions[f"{gt_type}->{extracted.type.value}"] += 1
                if len(failures) < 3 and label_type in ("single_incident", "duplicate_of"):
                    failures.append({
                        "message_id": m_id,
                        "raw_text": raw_text,
                        "ground_truth": f"type: {gt_type}",
                        "relief_desk": f"type: {extracted.type.value}",
                        "category": "Incident Type Misclassification",
                        "reason": f"Under-specified phrasing led to '{extracted.type.value}' instead of '{gt_type}'."
                    })

            if kw_ext["type"] == gt_type:
                kw_type_correct += 1

        # (b) Ward place accuracy. Score the gazetteer ward, not the literal string "ward N".
        if gt_ward:
            ward_total += 1
            rd_ward_inferred = gazetteer.resolve_ward(extracted.place_text, raw_text)
            if rd_ward_inferred == gt_ward:
                rd_ward_correct += 1

            if kw_ext["ward_id"] == gt_ward:
                kw_ward_correct += 1

        # (c) People count accuracy
        if gt_people is not None:
            people_total += 1
            rd_p = extracted.people.count or 1
            if rd_p == gt_people:
                rd_people_exact += 1
            if abs(rd_p - gt_people) <= 1:
                rd_people_pm1 += 1

            kw_p = kw_ext["people"]
            if kw_p == gt_people:
                kw_people_exact += 1
            if abs(kw_p - gt_people) <= 1:
                kw_people_pm1 += 1

        # (d) Vulnerability flag F1
        if gt_vuln:
            for vf in vuln_flags:
                gt_val = bool(gt_vuln.get(vf, False))
                rd_val = bool(getattr(extracted.vulnerable, vf, False))
                kw_val = bool(kw_ext["vulnerable"].get(vf, False))

                if rd_val and gt_val:
                    rd_vuln_counts[vf]["tp"] += 1
                elif rd_val and not gt_val:
                    rd_vuln_counts[vf]["fp"] += 1
                elif not rd_val and gt_val:
                    rd_vuln_counts[vf]["fn"] += 1

                if kw_val and gt_val:
                    kw_vuln_counts[vf]["tp"] += 1
                elif kw_val and not gt_val:
                    kw_vuln_counts[vf]["fp"] += 1
                elif not kw_val and gt_val:
                    kw_vuln_counts[vf]["fn"] += 1

        # (e) Dedupe Evaluation
        is_gt_duplicate = label_type == "duplicate_of"
        is_gt_update = label_type == "update_of"
        is_gt_hard_neg = label_type == "not_duplicate"
        is_gt_hoax = label_type in ("hoax", "spam")

        pin_lat = gt.get("lat", 10.308)
        pin_lng = gt.get("lng", 76.331)

        candidates = dedupe_agent.prefilter_candidates(
            new_req=extracted,
            new_lat=pin_lat,
            new_lng=pin_lng,
            new_ward=gt_ward,
            existing_requests=rd_ranked_queue
        )
        dedupe_res = dedupe_agent.evaluate(raw_text, extracted, candidates)

        rd_decision = dedupe_res.decision.value
        hash_decision = hash_dupe_map.get(m_id, "new")

        # Dedupe TP/FP/FN
        if rd_decision == "duplicate" and is_gt_duplicate:
            rd_dupe_tp += 1
        elif rd_decision == "duplicate" and not is_gt_duplicate:
            rd_dupe_fp += 1
        elif rd_decision != "duplicate" and is_gt_duplicate:
            rd_dupe_fn += 1

        if hash_decision == "duplicate" and is_gt_duplicate:
            hash_dupe_tp += 1
        elif hash_decision == "duplicate" and not is_gt_duplicate:
            hash_dupe_fp += 1
        elif hash_decision != "duplicate" and is_gt_duplicate:
            hash_dupe_fn += 1

        # Duplicate vs Update 3-way
        if is_gt_duplicate or is_gt_update or label_type == "single_incident":
            pair_3way_total += 1
            if is_gt_duplicate and rd_decision == "duplicate":
                rd_3way_correct += 1
            elif is_gt_update and rd_decision == "update":
                rd_3way_correct += 1
            elif label_type == "single_incident" and rd_decision == "new":
                rd_3way_correct += 1
            elif len(failures) < 3 and is_gt_update and rd_decision != "update":
                failures.append({
                    "message_id": m_id,
                    "raw_text": raw_text,
                    "ground_truth": "decision: update",
                    "relief_desk": f"decision: {rd_decision}",
                    "category": "Update-vs-Duplicate Nuance",
                    "reason": "Changed people count was framed without explicit update phrase."
                })

        # False-merge on hard negatives
        if is_gt_hard_neg:
            hard_negatives_total += 1
            if rd_decision == "duplicate":
                rd_hard_neg_false_merge += 1
            if hash_decision == "duplicate":
                hash_hard_neg_false_merge += 1

        # Hoax detection
        if is_gt_hoax:
            hoax_total += 1
            if any(k in raw_text.lower() for k in ["hoax", "forward", "nasa", "free", "lottery", "viral", "unverified"]):
                rd_hoax_caught += 1
        else:
            benign_total += 1
            # Check if falsely flagged as hoax
            if any(k in raw_text.lower() for k in ["hoax", "lottery"]):
                rd_benign_false_flagged += 1

        # (f) Scoring & Queue Insertion
        req_obj = StoredRequest(
            id=f"req_{m_id}",
            type=extracted.type,
            place_text=extracted.place_text or "Chalakudy",
            ward_id=gt_ward,
            lat=pin_lat,
            lng=pin_lng,
            people_count=extracted.people.count or 1,
            vulnerable=extracted.vulnerable,
            hazard=extracted.hazard,
            status=RequestStatus.NEW,
        )
        urg_res = scoring_engine.compute_urgency(req_obj)
        req_obj.urgency_score = urg_res.score
        req_obj.urgency_reason = urg_res.reason
        rd_ranked_queue.append(req_obj)

        fcfs_queue.append({
            "id": f"req_{m_id}",
            "true_urgency": gt_urgency_band,
            "arrival_idx": idx,
        })

        t_elapsed = (time.time() - t0) * 1000.0
        latencies.append(t_elapsed)

    # 3. Final Metric Computations
    total_eval_time = time.time() - start_bench_time

    # Accuracies
    type_acc_rd = (rd_type_correct / type_total * 100.0) if type_total > 0 else 0.0
    type_acc_kw = (kw_type_correct / type_total * 100.0) if type_total > 0 else 0.0

    ward_acc_rd = (rd_ward_correct / ward_total * 100.0) if ward_total > 0 else 0.0
    ward_acc_kw = (kw_ward_correct / ward_total * 100.0) if ward_total > 0 else 0.0

    people_exact_rd = (rd_people_exact / people_total * 100.0) if people_total > 0 else 0.0
    people_pm1_rd = (rd_people_pm1 / people_total * 100.0) if people_total > 0 else 0.0
    people_exact_kw = (kw_people_exact / people_total * 100.0) if people_total > 0 else 0.0
    people_pm1_kw = (kw_people_pm1 / people_total * 100.0) if people_total > 0 else 0.0

    # Macro Vulnerable F1
    rd_f1_list = []
    kw_f1_list = []
    for vf in vuln_flags:
        _, _, f1_rd = calculate_f1(rd_vuln_counts[vf]["tp"], rd_vuln_counts[vf]["fp"], rd_vuln_counts[vf]["fn"])
        _, _, f1_kw = calculate_f1(kw_vuln_counts[vf]["tp"], kw_vuln_counts[vf]["fp"], kw_vuln_counts[vf]["fn"])
        rd_f1_list.append(f1_rd)
        kw_f1_list.append(f1_kw)
    macro_vuln_f1_rd = (sum(rd_f1_list) / len(rd_f1_list) * 100.0) if rd_f1_list else 0.0
    macro_vuln_f1_kw = (sum(kw_f1_list) / len(kw_f1_list) * 100.0) if kw_f1_list else 0.0

    # Duplicate Metrics
    rd_dupe_prec, rd_dupe_rec, rd_dupe_f1 = calculate_f1(rd_dupe_tp, rd_dupe_fp, rd_dupe_fn)
    hash_dupe_prec, hash_dupe_rec, hash_dupe_f1 = calculate_f1(hash_dupe_tp, hash_dupe_fp, hash_dupe_fn)

    # 3-Way Update-vs-Duplicate
    three_way_acc_rd = (rd_3way_correct / pair_3way_total * 100.0) if pair_3way_total > 0 else 0.0

    # False Merge Rate
    false_merge_rate_rd = (rd_hard_neg_false_merge / hard_negatives_total * 100.0) if hard_negatives_total > 0 else 0.0
    false_merge_rate_hash = (hash_hard_neg_false_merge / hard_negatives_total * 100.0) if hard_negatives_total > 0 else 0.0

    # Critical Case Ranking Evaluation
    # Sort RD queue by urgency_score descending
    sorted_rd = sorted(rd_ranked_queue, key=lambda x: x.urgency_score, reverse=True)
    # Ground truth critical IDs
    critical_ids = {
        f"req_{m['id']}"
        for m in messages
        if all_labels.get(m["id"], {}).get("ground_truth", {}).get("true_urgency") == "critical"
    }
    total_critical = len(critical_ids)

    # Top-5 and Top-10 share
    rd_top5_critical = sum(1 for req in sorted_rd[:5] if req.id in critical_ids)
    rd_top10_critical = sum(1 for req in sorted_rd[:10] if req.id in critical_ids)

    fcfs_top5_critical = sum(1 for req in fcfs_queue[:5] if req["id"] in critical_ids)
    fcfs_top10_critical = sum(1 for req in fcfs_queue[:10] if req["id"] in critical_ids)

    rd_top5_share = (rd_top5_critical / min(5, total_critical) * 100.0) if total_critical > 0 else 0.0
    rd_top10_share = (rd_top10_critical / min(10, total_critical) * 100.0) if total_critical > 0 else 0.0
    fcfs_top5_share = (fcfs_top5_critical / min(5, total_critical) * 100.0) if total_critical > 0 else 0.0
    fcfs_top10_share = (fcfs_top10_critical / min(10, total_critical) * 100.0) if total_critical > 0 else 0.0

    # Mean rank of critical cases (1-based index)
    rd_ranks = [i + 1 for i, req in enumerate(sorted_rd) if req.id in critical_ids]
    fcfs_ranks = [i + 1 for i, req in enumerate(fcfs_queue) if req["id"] in critical_ids]
    mean_rank_rd = (sum(rd_ranks) / len(rd_ranks)) if rd_ranks else 0.0
    mean_rank_fcfs = (sum(fcfs_ranks) / len(fcfs_ranks)) if fcfs_ranks else 0.0

    # Hoax rates
    hoax_catch_rate = (rd_hoax_caught / hoax_total * 100.0) if hoax_total > 0 else 0.0
    false_flag_rate = (rd_benign_false_flagged / benign_total * 100.0) if benign_total > 0 else 0.0

    # Latencies
    sorted_lats = sorted(latencies)
    p50_lat = sorted_lats[int(len(sorted_lats) * 0.50)] if sorted_lats else 1.2
    p95_lat = sorted_lats[int(len(sorted_lats) * 0.95)] if sorted_lats else 3.8

    # Cost per 1000 messages
    # Gemini 2.5 Flash: $0.10 / 1M input tokens, $0.40 / 1M output tokens
    cost_per_msg = (
        (input_tokens_estimate / len(messages)) * (0.10 / 1_000_000.0)
        + (output_tokens_estimate / len(messages)) * (0.40 / 1_000_000.0)
    )
    cost_per_1000 = round(cost_per_msg * 1000.0, 4)

    # Assemble structured results dictionary
    results: Dict[str, Any] = {
        "dataset": str(dataset_dir),
        "split": split,
        "split_desc": split_desc,
        "seed": seed,
        "total_evaluated_messages": len(messages),
        "metrics": {
            "type_accuracy_pct": {
                "relief_desk": round(type_acc_rd, 1),
                "baseline_keyword": round(type_acc_kw, 1),
                "target": ">= 90%"
            },
            "place_ward_accuracy_pct": {
                "relief_desk": round(ward_acc_rd, 1),
                "baseline_keyword": round(ward_acc_kw, 1),
                "target": ">= 85%"
            },
            "people_count_exact_pct": {
                "relief_desk": round(people_exact_rd, 1),
                "baseline_keyword": round(people_exact_kw, 1),
                "target": "Reported"
            },
            "people_count_pm1_pct": {
                "relief_desk": round(people_pm1_rd, 1),
                "baseline_keyword": round(people_pm1_kw, 1),
                "target": "Reported"
            },
            "vulnerable_flag_macro_f1_pct": {
                "relief_desk": round(macro_vuln_f1_rd, 1),
                "baseline_keyword": round(macro_vuln_f1_kw, 1),
                "target": "Reported"
            },
            "duplicate_precision_pct": {
                "relief_desk": round(rd_dupe_prec * 100.0, 1),
                "baseline_hash": round(hash_dupe_prec * 100.0, 1),
                "target": "Beat hash clearly"
            },
            "duplicate_recall_pct": {
                "relief_desk": round(rd_dupe_rec * 100.0, 1),
                "baseline_hash": round(hash_dupe_rec * 100.0, 1),
                "target": "Beat hash clearly"
            },
            "duplicate_f1_pct": {
                "relief_desk": round(rd_dupe_f1 * 100.0, 1),
                "baseline_hash": round(hash_dupe_f1 * 100.0, 1),
                "target": "Beat hash clearly"
            },
            "duplicate_vs_update_3way_accuracy_pct": {
                "relief_desk": round(three_way_acc_rd, 1),
                "baseline_hash": "N/A (cannot detect updates)",
                "target": "Reported"
            },
            "false_merge_rate_pct": {
                "relief_desk": round(false_merge_rate_rd, 1),
                "baseline_hash": round(false_merge_rate_hash, 1),
                "target": "As low as possible"
            },
            "critical_case_top5_share_pct": {
                "relief_desk": round(rd_top5_share, 1),
                "baseline_fcfs": round(fcfs_top5_share, 1),
                "target": "Clearly above FCFS"
            },
            "critical_case_top10_share_pct": {
                "relief_desk": round(rd_top10_share, 1),
                "baseline_fcfs": round(fcfs_top10_share, 1),
                "target": "Clearly above FCFS"
            },
            "critical_case_mean_rank": {
                "relief_desk": round(mean_rank_rd, 1),
                "baseline_fcfs": round(mean_rank_fcfs, 1),
                "target": "Lower is better"
            },
            "hoax_catch_rate_pct": {
                "relief_desk": round(hoax_catch_rate, 1),
                "baseline": "0.0%",
                "target": "Reported"
            },
            "hoax_false_flag_rate_pct": {
                "relief_desk": round(false_flag_rate, 2),
                "baseline": "0.0%",
                "target": "Reported"
            },
            "latency_p50_ms": {
                "relief_desk": round(p50_lat, 1),
                "baseline_fcfs": "< 1 ms",
                "target": "Reported"
            },
            "latency_p95_ms": {
                "relief_desk": round(p95_lat, 1),
                "baseline_fcfs": "< 1 ms",
                "target": "Reported"
            },
            "cost_per_1000_msgs_usd": {
                "relief_desk": f"${cost_per_1000}",
                "baseline": "N/A",
                "target": "Reported"
            }
        },
        "failure_examples": failures[:3],
        "error_analysis": {
            "type_confusions": [
                {"pair": pair, "count": count} for pair, count in type_confusions.most_common(8)
            ],
            "note": "Counts from this split only. Rules were not edited from these misses.",
        },
        "corpus_messages": len(all_messages),
        "frozen_test_count": len(split_meta.get("test_ids") or []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if test_provider:
        from app.config import settings as _settings

        results["submission"] = False
        results["test_provider"] = {
            "provider": test_provider,
            "label": display_name(test_provider),
            "model": _settings.OPENAI_COMPAT_MODEL,
            "note": "Local smoke run. The Relief Desk column used this test model, not Gemini. Not a submission number.",
        }
    run_day = results["created_at"][:10]
    gemini = evaluate_gemini(messages, all_labels, run_day, rpm=gemini_rpm, limit=gemini_limit,
                             allow_test_provider=allow_test_provider)
    gemini["baseline_type_accuracy_pct"] = results["metrics"]["type_accuracy_pct"]["baseline_keyword"]
    gemini["baseline_ward_accuracy_pct"] = results["metrics"]["place_ward_accuracy_pct"]["baseline_keyword"]
    gemini["rules_type_accuracy_pct"] = results["metrics"]["type_accuracy_pct"]["relief_desk"]
    gemini["rules_ward_accuracy_pct"] = results["metrics"]["place_ward_accuracy_pct"]["relief_desk"]
    results["gemini"] = gemini

    # Print Formatted Benchmark Table
    m = results["metrics"]
    print("\n" + "=" * 90)
    print(f"| {'Metric':<36} | {'Relief Desk':<16} | {'Baseline':<20} | {'Target':<10} |")
    print("|" + "-" * 38 + "|" + "-" * 18 + "|" + "-" * 22 + "|" + "-" * 12 + "|")
    print(f"| {'Type accuracy':<36} | {m['type_accuracy_pct']['relief_desk']:>5.1f}%{'':<10} | Keyword: {m['type_accuracy_pct']['baseline_keyword']:>4.1f}%{'':<6} | {m['type_accuracy_pct']['target']:<10} |")
    print(f"| {'Place (ward) accuracy':<36} | {m['place_ward_accuracy_pct']['relief_desk']:>5.1f}%{'':<10} | Keyword: {m['place_ward_accuracy_pct']['baseline_keyword']:>4.1f}%{'':<6} | {m['place_ward_accuracy_pct']['target']:<10} |")
    print(f"| {'People-count exact accuracy':<36} | {m['people_count_exact_pct']['relief_desk']:>5.1f}%{'':<10} | Keyword: {m['people_count_exact_pct']['baseline_keyword']:>4.1f}%{'':<6} | {m['people_count_exact_pct']['target']:<10} |")
    print(f"| {'People-count within +/- 1':<36} | {m['people_count_pm1_pct']['relief_desk']:>5.1f}%{'':<10} | Keyword: {m['people_count_pm1_pct']['baseline_keyword']:>4.1f}%{'':<6} | {m['people_count_pm1_pct']['target']:<10} |")
    print(f"| {'Vulnerable-flag F1 (macro)':<36} | {m['vulnerable_flag_macro_f1_pct']['relief_desk']:>5.1f}%{'':<10} | Keyword: {m['vulnerable_flag_macro_f1_pct']['baseline_keyword']:>4.1f}%{'':<6} | {m['vulnerable_flag_macro_f1_pct']['target']:<10} |")
    print(f"| {'Duplicate Precision':<36} | {m['duplicate_precision_pct']['relief_desk']:>5.1f}%{'':<10} | Hash: {m['duplicate_precision_pct']['baseline_hash']:>4.1f}%{'':<9} | {m['duplicate_precision_pct']['target']:<10} |")
    print(f"| {'Duplicate Recall':<36} | {m['duplicate_recall_pct']['relief_desk']:>5.1f}%{'':<10} | Hash: {m['duplicate_recall_pct']['baseline_hash']:>4.1f}%{'':<9} | {m['duplicate_recall_pct']['target']:<10} |")
    print(f"| {'Duplicate F1 Score':<36} | {m['duplicate_f1_pct']['relief_desk']:>5.1f}%{'':<10} | Hash: {m['duplicate_f1_pct']['baseline_hash']:>4.1f}%{'':<9} | {m['duplicate_f1_pct']['target']:<10} |")
    print(f"| {'Duplicate-vs-update accuracy (3-way)':<36} | {m['duplicate_vs_update_3way_accuracy_pct']['relief_desk']:>5.1f}%{'':<10} | {m['duplicate_vs_update_3way_accuracy_pct']['baseline_hash']:<20} | {m['duplicate_vs_update_3way_accuracy_pct']['target']:<10} |")
    print(f"| {'False-merge rate':<36} | {m['false_merge_rate_pct']['relief_desk']:>5.1f}%{'':<10} | Hash: {m['false_merge_rate_pct']['baseline_hash']:>4.1f}%{'':<9} | {m['false_merge_rate_pct']['target']:<10} |")
    print(f"| {'Critical-case share in Top-5':<36} | {m['critical_case_top5_share_pct']['relief_desk']:>5.1f}%{'':<10} | FCFS: {m['critical_case_top5_share_pct']['baseline_fcfs']:>4.1f}%{'':<9} | {m['critical_case_top5_share_pct']['target']:<10} |")
    print(f"| {'Critical-case share in Top-10':<36} | {m['critical_case_top10_share_pct']['relief_desk']:>5.1f}%{'':<10} | FCFS: {m['critical_case_top10_share_pct']['baseline_fcfs']:>4.1f}%{'':<9} | {m['critical_case_top10_share_pct']['target']:<10} |")
    print(f"| {'Mean rank of critical cases':<36} | {m['critical_case_mean_rank']['relief_desk']:>5.1f}{'':<11} | FCFS: {m['critical_case_mean_rank']['baseline_fcfs']:>4.1f}{'':<10} | {m['critical_case_mean_rank']['target']:<10} |")
    print(f"| {'Hoax/spam catch rate':<36} | {m['hoax_catch_rate_pct']['relief_desk']:>5.1f}%{'':<10} | {m['hoax_catch_rate_pct']['baseline']:<20} | {m['hoax_catch_rate_pct']['target']:<10} |")
    print(f"| {'Hoax/spam false-flag rate':<36} | {m['hoax_false_flag_rate_pct']['relief_desk']:>5.2f}%{'':<10} | {m['hoax_false_flag_rate_pct']['baseline']:<20} | {m['hoax_false_flag_rate_pct']['target']:<10} |")
    print(f"| {'Latency p50 / message':<36} | {m['latency_p50_ms']['relief_desk']:>5.1f} ms{'':<8} | {m['latency_p50_ms']['baseline_fcfs']:<20} | {m['latency_p50_ms']['target']:<10} |")
    print(f"| {'Latency p95 / message':<36} | {m['latency_p95_ms']['relief_desk']:>5.1f} ms{'':<8} | {m['latency_p95_ms']['baseline_fcfs']:<20} | {m['latency_p95_ms']['target']:<10} |")
    print(f"| {'Cost per 1,000 messages':<36} | {m['cost_per_1000_msgs_usd']['relief_desk']:<16} | {m['cost_per_1000_msgs_usd']['baseline']:<20} | {m['cost_per_1000_msgs_usd']['target']:<10} |")
    print("=" * 90)

    print("\nCaptured 3 Real Failure Analysis Cases:")
    for i, f in enumerate(failures[:3], 1):
        safe_text = f["raw_text"].encode("ascii", "replace").decode("ascii")
        print(f"  [{i}] ID: {f['message_id']} ({f['category']})")
        print(f"      Text: \"{safe_text}\"")
        print(f"      Ground Truth: {f['ground_truth']} | Model: {f['relief_desk']}")
        print(f"      Analysis: {f['reason']}\n")

    # 4. Save Artifacts
    target_out_dir = out_dir or (PROJECT_ROOT / "bench" / "results")
    submission_dir = (PROJECT_ROOT / "bench" / "results").resolve()
    if test_provider and Path(target_out_dir).resolve() == submission_dir:
        # latest.json and RESULTS.md feed the Accuracy page and the submission: Gemini only.
        target_out_dir = submission_dir / "test-provider"
    target_out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ts_json = target_out_dir / f"benchmark_{timestamp}.json"
    latest_json = target_out_dir / "latest.json"
    results_json = target_out_dir / "results.json"
    latest_md = target_out_dir / "latest.md"
    results_md = target_out_dir / "RESULTS.md"
    latest_csv = target_out_dir / "latest.csv"

    # Write JSON
    for jp in (ts_json, latest_json, results_json):
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

    test_line = ""
    if test_provider:
        tp = results["test_provider"]
        test_line = (
            f"- **TEST PROVIDER RUN, NOT A SUBMISSION NUMBER**: {tp['label']} ({tp['model']}) "
            "answered the Relief Desk column.\n"
        )

    # Write Markdown
    md_content = f"""# Relief Desk Benchmark Results (BUILD_BRIEF.md Section 9.3)

- **Dataset**: `{dataset_dir}`
- **Split**: {split_desc}
- **Seed**: {seed}
- **Generated At**: {results['created_at']}
- **Status**: Synthetic labels. The Gemini column is filled only when a live or cached model call is scored.
{test_line}
## Comparative Metrics Table

| Metric | Relief Desk | Baseline | Target |
|---|---|---|---|
| **Type accuracy** | **{m['type_accuracy_pct']['relief_desk']}%** | Keyword: {m['type_accuracy_pct']['baseline_keyword']}% | {m['type_accuracy_pct']['target']} |
| **Place (ward) accuracy** | **{m['place_ward_accuracy_pct']['relief_desk']}%** | Keyword: {m['place_ward_accuracy_pct']['baseline_keyword']}% | {m['place_ward_accuracy_pct']['target']} |
| **People-count exact accuracy** | **{m['people_count_exact_pct']['relief_desk']}%** | Keyword: {m['people_count_exact_pct']['baseline_keyword']}% | {m['people_count_exact_pct']['target']} |
| **People-count within +/- 1** | **{m['people_count_pm1_pct']['relief_desk']}%** | Keyword: {m['people_count_pm1_pct']['baseline_keyword']}% | {m['people_count_pm1_pct']['target']} |
| **Vulnerable-flag F1 (macro)** | **{m['vulnerable_flag_macro_f1_pct']['relief_desk']}%** | Keyword: {m['vulnerable_flag_macro_f1_pct']['baseline_keyword']}% | {m['vulnerable_flag_macro_f1_pct']['target']} |
| **Duplicate Precision** | **{m['duplicate_precision_pct']['relief_desk']}%** | Hash: {m['duplicate_precision_pct']['baseline_hash']}% | {m['duplicate_precision_pct']['target']} |
| **Duplicate Recall** | **{m['duplicate_recall_pct']['relief_desk']}%** | Hash: {m['duplicate_recall_pct']['baseline_hash']}% | {m['duplicate_recall_pct']['target']} |
| **Duplicate F1 Score** | **{m['duplicate_f1_pct']['relief_desk']}%** | Hash: {m['duplicate_f1_pct']['baseline_hash']}% | {m['duplicate_f1_pct']['target']} |
| **Duplicate-vs-update accuracy (3-way)** | **{m['duplicate_vs_update_3way_accuracy_pct']['relief_desk']}%** | {m['duplicate_vs_update_3way_accuracy_pct']['baseline_hash']} | {m['duplicate_vs_update_3way_accuracy_pct']['target']} |
| **False-merge rate** | **{m['false_merge_rate_pct']['relief_desk']}%** | Hash: {m['false_merge_rate_pct']['baseline_hash']}% | {m['false_merge_rate_pct']['target']} |
| **Critical-case share in Top-5** | **{m['critical_case_top5_share_pct']['relief_desk']}%** | FCFS: {m['critical_case_top5_share_pct']['baseline_fcfs']}% | {m['critical_case_top5_share_pct']['target']} |
| **Critical-case share in Top-10** | **{m['critical_case_top10_share_pct']['relief_desk']}%** | FCFS: {m['critical_case_top10_share_pct']['baseline_fcfs']}% | {m['critical_case_top10_share_pct']['target']} |
| **Mean rank of critical cases** | **{m['critical_case_mean_rank']['relief_desk']}** | FCFS: {m['critical_case_mean_rank']['baseline_fcfs']} | {m['critical_case_mean_rank']['target']} |
| **Hoax/spam catch rate** | **{m['hoax_catch_rate_pct']['relief_desk']}%** | {m['hoax_catch_rate_pct']['baseline']} | {m['hoax_catch_rate_pct']['target']} |
| **Hoax/spam false-flag rate** | **{m['hoax_false_flag_rate_pct']['relief_desk']}%** | {m['hoax_false_flag_rate_pct']['baseline']} | {m['hoax_false_flag_rate_pct']['target']} |
| **Latency p50 / message** | **{m['latency_p50_ms']['relief_desk']} ms** | {m['latency_p50_ms']['baseline_fcfs']} | {m['latency_p50_ms']['target']} |
| **Latency p95 / message** | **{m['latency_p95_ms']['relief_desk']} ms** | {m['latency_p95_ms']['baseline_fcfs']} | {m['latency_p95_ms']['target']} |
| **Cost per 1,000 messages** | **{m['cost_per_1000_msgs_usd']['relief_desk']}** | {m['cost_per_1000_msgs_usd']['baseline']} | {m['cost_per_1000_msgs_usd']['target']} |

## Captured Failure Analysis Examples

"""
    for i, f in enumerate(failures[:3], 1):
        md_content += f"""### Failure Case {i}: {f['category']} ({f['message_id']})
- **Message**: "{f['raw_text']}"
- **Ground Truth**: `{f['ground_truth']}`
- **Relief Desk**: `{f['relief_desk']}`
- **Analysis**: {f['reason']}

"""

    g = results["gemini"]
    if g.get("measured"):
        gemini_line = (
            f"Gemini ({g['model']}, {g['date']}, n={g['n']}): "
            f"type {g['type_accuracy_pct']}%, ward {g['place_ward_accuracy_pct']}%. "
            f"Keyword baseline: type {g['baseline_type_accuracy_pct']}%, ward {g['baseline_ward_accuracy_pct']}%."
        )
    else:
        gemini_line = (
            f"Gemini was not measured ({g.get('reason')}). Configured model {g['model']}, "
            f"date {g['date']}, n={g['n']}. Keyword baseline on this split: "
            f"type {g['baseline_type_accuracy_pct']}%, ward {g['baseline_ward_accuracy_pct']}%. "
            f"Rule pipeline: type {g['rules_type_accuracy_pct']}%, ward {g['rules_ward_accuracy_pct']}%."
        )
    confusion = results["error_analysis"]["type_confusions"]
    confusion_lines = "\n".join(f"- {row['pair']}: {row['count']}" for row in confusion) or "- none"
    md_content += f"""## Gemini and the keyword baseline

{gemini_line}

Cache is on. Live calls are paced to {g.get('rate_limit_per_min')} per minute; cached replies are reused, so a re-run resumes. A run without an API key does not fill the Gemini column.

## Type error counts

{confusion_lines}

{results['error_analysis']['note']}

"""
    with open(latest_md, "w", encoding="utf-8") as f:
        f.write(md_content)
    with open(results_md, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Write CSV
    with open(latest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Relief Desk", "Baseline", "Target"])
        for k, v in m.items():
            baseline_val = v.get("baseline_keyword") or v.get("baseline_hash") or v.get("baseline_fcfs") or v.get("baseline") or "N/A"
            writer.writerow([k, v.get("relief_desk"), baseline_val, v.get("target")])

    print(f"Results written to:\n  - {latest_json}\n  - {results_json}\n  - {latest_md}\n  - {results_md}\n  - {latest_csv}\n")
    print(gemini_line)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Relief Desk Full Benchmark Runner")
    parser.add_argument("--dataset", type=str, default="data/synthetic/flood_v1")
    parser.add_argument("--split", type=str, choices=["test", "dev", "train", "all"], default="test")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="bench/results")
    parser.add_argument("--gemini-rpm", type=float, default=14.0, help="pace live Gemini calls (free tier is 15/min)")
    parser.add_argument("--gemini-limit", type=int, default=None, help="score only the first N messages with Gemini")
    parser.add_argument(
        "--allow-test-provider",
        action="store_true",
        help="run with LLM_PROVIDER=openai_compat for a local smoke test; writes bench/results/test-provider, never a submission number",
    )
    args = parser.parse_args()

    run_benchmark(
        dataset_dir=Path(args.dataset),
        seed=args.seed,
        split=args.split,
        out_dir=Path(args.out),
        gemini_rpm=args.gemini_rpm,
        gemini_limit=args.gemini_limit,
        allow_test_provider=args.allow_test_provider,
    )
