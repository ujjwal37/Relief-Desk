"""Merge-flag precision/recall on the labelled flood_v1 set. Rules only (AI_MODE fallback, no Gemini).

A flag is correct when the flagged case and its target carry the same labelled incident.
Recall counts duplicate_of messages flagged to any case of their incident.
"""
import json, os, sys, pathlib
os.environ["GEMINI_API_KEY"] = "replace-me"
os.environ.setdefault("JWT_SECRET", "bench-only")
os.environ["AI_MODE"] = "fallback"
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))
import app.agents.pipeline as pl
pl._spawn = lambda fn: fn()
from fastapi.testclient import TestClient
from app.main import app
from app.tools.storage import storage_service

data = ROOT / "data" / "synthetic" / "flood_v1"
msgs = [json.loads(l) for l in (data / "messages.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
labels = {r["message_id"]: r for r in map(json.loads, (data / "labels.jsonl").read_text(encoding="utf-8").splitlines()) if r}
client = TestClient(app)
pre = {r.id for r in storage_service.list_requests()}
req_of, inc_of = {}, {}
for m in msgs:
    res = client.post("/api/reports", json={"text": m["text"], "raw_text": m["text"], "lang": m.get("lang", "en"),
                      "channel": "text", "idempotency_key": f"bench-{m['id']}", "source_id": f"bench_{m['id']}"})
    if res.status_code != 200:
        continue
    rid = res.json()["request_id"]
    req_of[m["id"]] = rid
    inc = (labels.get(m["id"]) or {}).get("ground_truth", {}).get("incident_id")
    if inc:
        inc_of[rid] = inc
tp = fp = 0
dups = [mid for mid, l in labels.items() if l["label_type"] == "duplicate_of" and mid in req_of]
hit = 0
for mid, rid in req_of.items():
    r = storage_service.get_request(rid)
    tgt = r.possible_duplicate.target_id if r and r.possible_duplicate else None
    if not tgt:
        continue
    same = tgt in inc_of and inc_of.get(rid) == inc_of[tgt]
    tp += same; fp += not same
    if mid in dups and same:
        hit += 1
out = {"mode": "rules_only_fallback", "messages": len(req_of), "duplicate_labels": len(dups),
       "flags": tp + fp, "precision": round(tp / (tp + fp), 3) if tp + fp else None,
       "recall": round(hit / len(dups), 3) if dups else None}
print(json.dumps(out))
