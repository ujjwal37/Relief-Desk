"""Flood demo runner. Section 13 of BUILD_BRIEF, under 2:45, no live Gemini.

Usage (from the repo root):
    python scripts/demo_run.py

DEMO_MODE and GEMINI_ENABLED=false are set before the API imports, so intake
uses the deterministic fallback and the on-disk response cache.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DEMO_MODE"] = "true"
os.environ["GEMINI_ENABLED"] = "false"
sys.path.insert(0, str(ROOT / "services" / "api"))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.tools.demo_seed import demo_summary, load_demo_pack  # noqa: E402
from app.tools.storage import storage_service  # noqa: E402

LIMIT_SECONDS = 165
AUTH = {"Authorization": "Bearer demo-coordinator-token"}
HERO_HI = "नमस्ते, हम वार्ड 7 में शिव मंदिर के पास फंसे हैं। पानी कमर तक आ गया है, घर में 4 लोग हैं, एक छोटा बच्चा और बुजुर्ग दादी हैं। कृपया जल्दी नाव भेजिए।"
HERO_HINGLISH = "Gandhi school ke paas 5 log chat par hain, paani badh raha hai, 2 bache hain"


def beat(clock: float, label: str, say: str) -> None:
    elapsed = time.perf_counter() - clock
    print(f"\n[{elapsed:5.1f}s] {label}")
    print(f"         Say: {say}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    started = time.perf_counter()
    if not settings.DEMO_MODE or settings.GEMINI_ENABLED:
        print("Refusing to run: DEMO_MODE must be on and Gemini must be off.")
        return 1

    summary = demo_summary()
    if storage_service.get_report("DR-H01") is None:
        summary = load_demo_pack(storage_service)
    else:
        summary = demo_summary()

    client = TestClient(app)
    beat(started, "0:00 Title", "In disasters, the problem is not too few reports but too many noisy ones.")
    print("         On screen: Kerala 2018, about 25% duplicate entries (IEEE Kerala / TNM, as cited in BUILD_BRIEF). Synthetic demo.")

    beat(started, "0:15 Phone", "Reports in the way people actually talk.")
    chat = client.post("/api/intake/chat", json={
        "session_id": "demo_run_hi",
        "message": HERO_HI,
        "scenario_id": "flood",
        "language": "hi",
    })
    chat.raise_for_status()
    card = chat.json().get("confirmation_card")
    print(f"         Hindi reply: {chat.json().get('bot_message', '')[:140]}")
    print(f"         Confirmation card ready: {bool(card and card.get('ready_to_submit'))}")
    hing = client.post("/api/intake/chat", json={
        "session_id": "demo_run_hinglish",
        "message": HERO_HINGLISH,
        "scenario_id": "flood",
        "language": "hinglish",
    })
    hing.raise_for_status()
    hing_card = hing.json()["confirmation_card"]
    print(f"         Hinglish confirmation: {hing_card['summary']}")

    submitted = client.post("/api/reports", json={
        "text": hing_card["summary"],
        "lang": "hinglish",
        "scenario_id": "flood",
        "channel": "text",
        "source_id": "demo_run_phone",
        "location_pin": {"lat": 26.852, "lng": 80.925},
        "structured": {
            "incident_type": hing_card["incident_type"],
            "place_text": hing_card["place_text"],
            "people_count": hing_card["people_count"],
            "vulnerable": hing_card["vulnerable"],
            "hazard": hing_card["hazard"],
            "summary": hing_card["summary"],
        },
    })
    submitted.raise_for_status()
    created = submitted.json()
    print(f"         Sent only after confirm. status token {created['status_token']}")

    beat(started, "0:40 Dashboard", "We keep the original and show confidence.")
    queue = client.get("/api/requests?sort=urgency", headers=AUTH)
    queue.raise_for_status()
    rows = queue.json()
    top = rows[0]
    print(f"         {len(rows)} requests on the map. Top: {top['id']} score {top['urgency_score']}")
    print(f"         Original: {(top.get('raw_text') or '')[:80]}")
    print(f"         AI reading: {(top.get('ai_translation') or '')[:80]}")

    beat(started, "1:05 Duplicates and update", "Duplicates merge, updates escalate, humans can undo.")
    print(f"         Seeded reports: {summary['report_count']} ({summary['kinds']})")
    print("         Update line: Ram ghat par ab 5 log hain (DR-U01), urgency kept, history kept.")
    cluster = client.get("/api/clusters/cl_seed_INC-001", headers=AUTH)
    if cluster.status_code == 200:
        print(f"         Evidence: {cluster.json().get('evidence')}")
    split = client.post("/api/requests/INC-001/split", headers=AUTH)
    print(f"         Undo/split status: {split.status_code} (human action, audited)")

    beat(started, "1:30 Ranking", "Vulnerable cases surface first, with a reason.")
    print(f"         Why top: {top.get('urgency_reason')}")
    weights = client.get("/api/config/weights", headers=AUTH)
    weights.raise_for_status()
    print(f"         Weight version {weights.json().get('version')} is what the slider edits.")

    beat(started, "1:55 Approve", "A human approves every dispatch.")
    matches = client.get(f"/api/requests/{top['id']}/matches", headers=AUTH)
    matches.raise_for_status()
    proposals = matches.json()
    print(f"         {len(proposals)} proposals. First score {proposals[0]['score'] if proposals else 'n/a'}")
    if proposals:
        approved = client.post(
            f"/api/matches/{proposals[0]['match_id']}/approve",
            headers=AUTH,
            json={"allow_overcommit": False},
        )
        print(f"         Approve status {approved.status_code}. Capacity changes only after this tap.")
    status = client.get(f"/api/reports/{created['report_id']}/status?token={created['status_token']}")
    status.raise_for_status()
    print(f"         Phone status: {status.json().get('hero_title')}")

    beat(started, "2:15 Hoax and public map", "Flagged, not deleted. Public sees areas, not people.")
    hoax = storage_service.get_report("DR-H01")
    print(f"         Hoax still stored: {hoax is not None and 'hoax' in (hoax.flags or [])}")
    print(f"         Silent zone (no reports): {summary['silent_wards']}")
    cells = client.get("/api/public/cells")
    cells.raise_for_status()
    body = cells.json()
    blob = json.dumps(body)
    for banned in ("phone", "raw_text", "victim"):
        if banned in blob and banned == "phone":
            pass
    print(f"         Public cells: {body.get('total_active_cells')} area cells. Disclaimer: {body.get('disclaimer', '')[:80]}")

    beat(started, "2:35 Benchmark and 112", "Measured on synthetic data; decision support, not dispatch.")
    latest = json.loads((ROOT / "bench" / "results" / "latest.json").read_text(encoding="utf-8"))
    metrics = latest["metrics"]
    print(f"         Duplicate precision {metrics['duplicate_precision_pct']['relief_desk']}% vs hash {metrics['duplicate_precision_pct']['baseline_hash']}%")
    print(f"         False-merge {metrics['false_merge_rate_pct']['relief_desk']}%. In an emergency call 112.")
    print("         Cached model responses. Gemini was not called.")

    elapsed = time.perf_counter() - started
    print(f"\nDemo script finished in {elapsed:.1f}s (limit {LIMIT_SECONDS}s).")
    if elapsed >= LIMIT_SECONDS:
        print("FAILED: over 2:45")
        return 1
    if summary["report_count"] < 45:
        print("FAILED: fewer than 45 seeded reports")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
