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
