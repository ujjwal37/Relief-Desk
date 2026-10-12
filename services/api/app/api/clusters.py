from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.tools.storage import storage_service
from app.models.firestore_models import StoredCluster, StoredRequest
from app.api.auth import get_current_coordinator, CoordinatorUser

router = APIRouter(prefix="/api", tags=["Requests & Clusters"])


def _parse_stamp(value: Optional[str]) -> Optional[datetime]:
    """Accept ISO timestamps, a trailing Z, and a '+' that the query string turned into a space."""
    if not value or not str(value).strip():
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if " " in text and "+" not in text:
        text = text.replace(" ", "+", 1)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _changed_since(req, updated_since: Optional[str]) -> bool:
    """A new report stays visible when a query string turns '+' into a space, or one stamp uses Z."""
    if not updated_since:
        return True
    raw = req.updated_at or req.created_at or ""
    mark = _parse_stamp(updated_since)
    if mark is None:
        return raw >= updated_since
    got = _parse_stamp(raw)
    if got is None:
        return raw >= updated_since
    return got >= mark


class MergeRequestPayload(BaseModel):
    secondary_request_id: str = Field(..., description="The ID of the request to merge into this one")
    evidence: List[str] = Field(default_factory=list, description="Concrete evidence reasons for merging")
    merged_by: str = Field(default="coordinator", description="Actor performing the merge")


class MergeResultResponse(BaseModel):
    cluster_id: str
    primary_request_id: str
    secondary_request_id: str
    evidence: List[str]
    merged_by: str


class SplitResultResponse(BaseModel):
    cluster_id: str
    restored_request_ids: List[str]
    undone: bool
    actor: str


@router.post("/requests/{request_id}/merge", response_model=MergeResultResponse)
def merge_requests(
    request_id: str,
    payload: MergeRequestPayload,
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    req_primary = storage_service.get_request(request_id)
    if not req_primary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Primary request '{request_id}' not found"
        )

    req_secondary = storage_service.get_request(payload.secondary_request_id)
    if not req_secondary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Secondary request '{payload.secondary_request_id}' not found"
        )

    cluster = storage_service.create_cluster(
        request_ids=[request_id, payload.secondary_request_id],
        evidence=payload.evidence or ["Manual coordinator merge"],
        merged_by=payload.merged_by or coordinator.email,
    )

    return MergeResultResponse(
        cluster_id=cluster.id,
        primary_request_id=request_id,
        secondary_request_id=payload.secondary_request_id,
        evidence=cluster.evidence,
        merged_by=cluster.merged_by
    )


@router.post("/requests/{request_id}/split", response_model=SplitResultResponse)
def split_request_cluster(
    request_id: str,
    actor: str = "coordinator",
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    req = storage_service.get_request(request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request '{request_id}' not found"
        )

    if not req.cluster_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request '{request_id}' is not currently part of any cluster"
        )

    cluster_id = req.cluster_id
    cluster = storage_service.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cluster '{cluster_id}' not found"
        )

    restored_ids = list(cluster.request_ids)
    split_cluster = storage_service.split_cluster(cluster_id, actor=actor or coordinator.email)

    return SplitResultResponse(
        cluster_id=cluster_id,
        restored_request_ids=restored_ids,
        undone=True,
        actor=actor
    )


@router.get("/clusters/{cluster_id}", response_model=StoredCluster)
def get_cluster_evidence(
    cluster_id: str,
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    cluster = storage_service.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cluster '{cluster_id}' not found"
        )
    return cluster


@router.get("/cases/{case_id}/trace")
def case_trace(
    case_id: str,
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    req = storage_service.get_request(case_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case '{case_id}' not found")
    from app.agents.pipeline import ensure_trace
    ensure_trace(req)
    return req.trace


@router.get("/cases/{case_id}/merge")
def case_merge(
    case_id: str,
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    """Quotes and dedupe evidence that are actually stored. Missing fields stay null."""
    req = storage_service.get_request(case_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case '{case_id}' not found")
    cluster = storage_service.get_cluster(req.cluster_id) if req.cluster_id else None
    ids = list(cluster.request_ids) if cluster and cluster.request_ids else [req.id]
    reports = []
    for rid in ids:
        member = storage_service.get_request(rid)
        linked = next((row for row in storage_service.list_reports() if row.request_id == rid), None)
        reports.append({
            "id": rid,
            "text": (member.raw_text if member else None) or (linked.raw_text if linked else None),
            "at": member.created_at if member else (linked.created_at if linked else None),
            "channel": linked.channel if linked else None,
            "lang": linked.lang if linked else None,
        })
    why = None
    for step in req.trace or []:
        if step.get("agent") == "Dedupe" and step.get("output"):
            why = step.get("output")
            break
    if why is None and cluster and cluster.evidence:
        why = " ".join(cluster.evidence)
    return {
        "count": req.merged_count or 1,
        "why": why,
        "reports": reports,
    }


@router.get("/requests", response_model=List[StoredRequest], summary="List ranked requests")
def list_requests(
    sort: str = "urgency",
    pack_id: Optional[str] = None,
    updated_since: Optional[str] = None,
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    reqs = [req for req in storage_service.list_requests() if not req.merged_into]
    if pack_id:
        reqs = [req for req in reqs if (req.pack_id or "flood") == pack_id]
    elif not reqs:
        storage_service.load_seed_incidents()
        reqs = [req for req in storage_service.list_requests() if not req.merged_into]

    from app.models.firestore_models import RequestStatus
    from app.tools.scoring import scoring_engine

    closed = {RequestStatus.COMPLETED, RequestStatus.RESOLVED, RequestStatus.CLOSED}
    from app.agents.pipeline import ensure_trace
    refreshed = []
    for req in reqs:
        ensure_trace(req)
        before = req.urgency_score
        if req.status not in closed:
            result = scoring_engine.compute_urgency(req)
            req.urgency_score = result.score
            req.urgency_reason = result.reason
            req.wait_points = result.breakdown.get("wait_points")
            req.wait_minutes = int(result.breakdown.get("wait_minutes") or 0)
        score_changed = req.urgency_score != before
        if _changed_since(req, updated_since) or score_changed:
            refreshed.append(req)

    if sort == "urgency":
        refreshed = sorted(refreshed, key=lambda r: r.urgency_score, reverse=True)
    return refreshed


@router.get("/requests/{id}", response_model=StoredRequest, summary="Get single request detail")
def get_request_detail(
    id: str,
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    req = storage_service.get_request(id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request '{id}' not found"
        )
    return req
