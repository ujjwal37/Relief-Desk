from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import DEMO_COORDINATOR_EMAIL, CoordinatorUser, get_current_coordinator
from app.config import settings
from app.tools.storage import storage_service

router = APIRouter(prefix="/api", tags=["Demo"])


@router.post("/demo/reset")
def reset_demo(coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    """Reload synthetic seeds into the running API.

    Allowed in demo mode, or for the synthetic demo coordinator account even when DEMO_MODE is off,
    so a judge can undo merges and dispatches between runs. Real coordinators get 403.
    """
    if not settings.DEMO_MODE and (coordinator.email or "").lower() != DEMO_COORDINATOR_EMAIL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo reset is only available in demo mode or for the demo coordinator")
    from app.tools.demo_surge import snapshot
    if snapshot()["running"]:
        raise HTTPException(status_code=409, detail="Wait for the synthetic surge to finish before resetting")
    summary = storage_service.reset_demo()
    summary["actor"] = coordinator.email
    return summary


@router.post("/demo/full")
def load_full_scenario(coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    """Load the full flood pack into the running demo. Reset returns to the small seed."""
    if not settings.DEMO_MODE and (coordinator.email or "").lower() != DEMO_COORDINATOR_EMAIL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo seed is only available in demo mode or for the demo coordinator")
    from app.tools.demo_surge import snapshot
    if snapshot()["running"]:
        raise HTTPException(status_code=409, detail="Wait for the synthetic surge to finish before reloading")
    summary = storage_service.load_full_scenario()
    summary["actor"] = coordinator.email
    return summary


def require_demo_mode():
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=403, detail="Synthetic demonstrations require DEMO_MODE")


class SurgeResponse(BaseModel):
    run_id: str
    running: bool
    submitted: int
    failed: int
    total: int


class ScenarioSeedResponse(BaseModel):
    pack_id: str
    loaded: bool


@router.post("/demo/simulate-surge", status_code=202, response_model=SurgeResponse)
def simulate_surge(coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    require_demo_mode()
    from app.tools.demo_surge import start_surge
    try:
        from app.api.reports import ReportSubmitRequest, submit_report
        return start_surge(coordinator.email, lambda data: submit_report(ReportSubmitRequest(**data)))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/demo/surge", response_model=SurgeResponse)
def surge_state(coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    require_demo_mode()
    from app.tools.demo_surge import snapshot
    return snapshot()


@router.post("/demo/scenario/{pack_id}", response_model=ScenarioSeedResponse)
def load_scenario(pack_id: str, coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    require_demo_mode()
    from app.tools.scenario_loader import scenario_registry
    if scenario_registry.get_scenario(pack_id) is None:
        raise HTTPException(status_code=404, detail="Unknown scenario pack")
    storage_service.load_missing_scenario(pack_id)
    storage_service.record_audit(actor=coordinator.email, action="demo_scenario_loaded", target=pack_id, after={"synthetic": True})
    return {"pack_id": pack_id, "loaded": True}


class SampleReportRequest(BaseModel):
    kind: str = "hindi"  # hindi | voice | photo | duplicate


@router.get("/demo/samples")
def list_samples():
    from app.tools.demo_samples import catalog
    return catalog()


@router.get("/demo/samples/{sample_id}")
def get_sample_file(sample_id: str):
    from fastapi.responses import FileResponse
    from app.tools.demo_samples import sample_path
    path = sample_path(sample_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Unknown sample")
    media = "audio/wav" if path.suffix == ".wav" else "image/jpeg"
    return FileResponse(path, media_type=media, filename=path.name)


@router.post("/demo/sample-report")
def submit_sample_report(payload: SampleReportRequest):
    """One-click synthetic sample through the normal intake pipeline."""
    from app.api.reports import ReportSubmitRequest, submit_report
    from app.tools.demo_samples import sample_payload
    from app.tools.storage import storage_service
    try:
        data = sample_payload(payload.kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if payload.kind.lower() == "duplicate":
        has_hindi = any("चालाकुडी" in (row.raw_text or "") for row in storage_service.list_requests() if not row.merged_into)
        if not has_hindi:
            submit_report(ReportSubmitRequest(**sample_payload("hindi")))
    return submit_report(ReportSubmitRequest(**data))
