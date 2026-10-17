import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import CoordinatorUser, get_current_coordinator

router = APIRouter(prefix="/api", tags=["Benchmark"])

RESULTS_PATH = Path(__file__).resolve().parents[4] / "bench" / "results" / "latest.json"


@router.get("/benchmark/latest")
def latest_benchmark(coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    if not RESULTS_PATH.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark results not found")
    return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))


@router.get("/benchmark/cost")
def measured_cost(coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    """Cost from measured numbers only: live Gemini reports that returned a token count.

    The rupee figure appears only when a per-token rate is configured; nothing is estimated.
    """
    from app.config import settings
    from app.tools.storage import storage_service

    rows = [
        r.ai for r in storage_service.list_requests()
        if r.ai is not None and r.ai.provider == "gemini" and not r.ai.cached and r.ai.tokens
    ]
    reports = len(rows)
    tokens = sum(int(a.tokens or 0) for a in rows)
    rate = settings.GEMINI_INR_PER_1M_TOKENS
    out = {"measured": reports > 0, "reports": reports, "tokens": tokens,
           "tokens_per_report": round(tokens / reports) if reports else None,
           "inr_per_report": None, "inr_per_1000_reports": None}
    if reports and rate:
        per = tokens / reports * float(rate) / 1_000_000
        out["inr_per_report"] = round(per, 4)
        out["inr_per_1000_reports"] = round(per * 1000, 2)
    return out
