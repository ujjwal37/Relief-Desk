from datetime import datetime, timedelta, timezone
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


class RecentReportItem(BaseModel):
    id: str
    case_id: str
    type: str
    summary: str
    ward_id: Optional[str] = None
    place_text: Optional[str] = None
    created_at: str
    joined_existing: bool = False


@router.get("/recent-reports", response_model=List[RecentReportItem], summary="Reports from the last few minutes")
def recent_reports(
    minutes: int = 15,
    _coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    """Newest first. A merge still points at the case already in the queue."""
    window = max(1, min(int(minutes or 15), 120))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window)
    rows: List[RecentReportItem] = []
    for report in storage_service.list_reports():
        stamp = _parse_stamp(report.created_at)
        if stamp is None or stamp < cutoff:
            continue
        case_id = report.case_id or report.request_id
        if not case_id:
            continue
        summary = (report.summary or report.raw_text or "").strip().replace("\n", " ")
        if len(summary) > 80:
            summary = summary[:77].rstrip() + "…"
        rows.append(
            RecentReportItem(
                id=report.id,
                case_id=case_id,
                type=report.incident_type or "other",
                summary=summary,
                ward_id=report.ward_id,
                place_text=report.place_text,
                created_at=report.created_at,
                joined_existing=bool(report.joined_existing),
            )
        )
    rows.sort(key=lambda row: row.created_at, reverse=True)
    return rows[:20]


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

    from app.tools.case_merge import fold_case

    try:
        fold_case(
            request_id,
            payload.secondary_request_id,
            evidence=payload.evidence or ["Manual coordinator merge"],
            merged_by=payload.merged_by or coordinator.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    req_primary = storage_service.get_request(request_id)
    cluster = storage_service.get_cluster(req_primary.cluster_id) if req_primary and req_primary.cluster_id else None
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Merge did not record a cluster")

    return MergeResultResponse(
        cluster_id=cluster.id,
        primary_request_id=request_id,
        secondary_request_id=payload.secondary_request_id,
        evidence=cluster.evidence,
        merged_by=cluster.merged_by
    )


@router.post("/requests/{request_id}/keep-separate")
def keep_request_separate(
    request_id: str,
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    """The coordinator looked at a possible duplicate and wants it to stay its own case."""
    req = storage_service.get_request(request_id)
    if req is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Request '{request_id}' not found")
    req.possible_duplicate = None
    req.dedupe_trace = "Kept separate."
    for step in req.trace or []:
        if step.get("agent") == "Dedupe":
            step["output"] = "Kept separate."
    storage_service.save_request(req, actor=coordinator.email or "coordinator")
    return {"id": req.id, "possible_duplicate": None, "dedupe_trace": req.dedupe_trace}


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
    from app.api.public import public_code_for
    reports = []
    if req.report_quotes:
        for quote in req.report_quotes:
            linked = storage_service.get_report(quote.report_id)
            reports.append({
                "id": public_code_for(quote.report_id), "internal_id": quote.report_id,
                "text": quote.text,
                "at": linked.created_at if linked else req.created_at,
                "channel": linked.channel if linked else None,
                "lang": linked.lang if linked else None,
            })
    else:
        ids = list(cluster.request_ids) if cluster and cluster.request_ids else [req.id]
        for rid in ids:
            member = storage_service.get_request(rid)
            linked = next((row for row in storage_service.list_reports() if row.request_id == rid), None)
            reports.append({
                "id": public_code_for(rid), "internal_id": rid,
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
    if req.dedupe_trace:
        why = req.dedupe_trace
    if req.count_note and (not why or req.count_note not in why):
        why = f"{why}. {req.count_note}" if why else req.count_note
    if why is None and cluster and cluster.evidence:
        why = " ".join(cluster.evidence)
    if why:
        import re as _re
        # The case's urgency is shown on the card; an older score in this text would contradict it.
        why = _re.sub(r",?\s*(?:with |and )?(?:an? )?urgency(?: score)?(?: of)? \d+(?:\.\d+)?", "", why, flags=_re.I).strip()
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

    closed = {RequestStatus.COMPLETED, RequestStatus.RESOLVED, RequestStatus.CLOSED, RequestStatus.DISMISSED_HOAX}
    from app.agents.pipeline import ensure_trace
    from app.tools.case_queue import refresh_queue, recheck_if_live
    capped = set(refresh_queue(reqs))
    rechecked = recheck_if_live(reqs)
    refreshed = []
    from app.api.public import public_code_for
    for req in reqs:
        ensure_trace(req)
        if not req.public_code:
            req.public_code = public_code_for(req.report_ids[0] if req.report_ids else req.id)
        from app.agents.depth import fill_depth
        fill_depth(req)
        _fix_place(req)
        before = req.urgency_score
        if req.status not in closed:
            result = scoring_engine.compute_urgency(req)
            req.urgency_score = result.score
            req.urgency_reason = result.reason
            req.wait_points = result.breakdown.get("wait_points")
            req.wait_minutes = int(result.breakdown.get("wait_minutes") or 0)
        score_changed = req.urgency_score != before
        if _changed_since(req, updated_since) or score_changed or req.id in capped:
            refreshed.append(req)
            if req.id in capped or req.id == rechecked:
                storage_service.save_request(req, actor="ai_queue")

    if sort == "urgency":
        refreshed = sorted(refreshed, key=lambda r: r.urgency_score, reverse=True)
    # A merge can land while this list is being built. Drop the copy that joined another case.
    visible = [req for req in refreshed if not req.merged_into]
    return _collapse_identical_hoaxes(visible)


def _collapse_identical_hoaxes(rows):
    """Identical hoax text is one row. This is not a same-place merge."""
    import re as _re
    seen = set()
    kept = []
    for req in rows:
        flags = set(req.flags or [])
        hoax = bool(getattr(req, "hoax_reason", None)) or bool(flags & {"hoax", "likely_hoax", "dismissed_hoax"})
        key = _re.sub(r"\s+", " ", (req.raw_text or "").strip().lower())
        if hoax and key:
            if key in seen:
                continue
            seen.add(key)
        kept.append(req)
    return kept


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
    from app.tools.case_queue import refresh_queue
    if refresh_queue([req]):
        storage_service.save_request(req, actor="ai_queue")
    return req


def _fix_place(req) -> None:
    """One place truth per case: ward comes from coordinates; a hoax with no place has no pin."""
    from app.tools.gazetteer import ward_for_point
    flags = set(req.flags or [])
    hoax = bool(getattr(req, "hoax_reason", None)) or bool(flags & {"likely_hoax", "hoax"})
    place = (req.place_text or "").strip()
    if place and len(place) > 60:
        # A whole sentence is not a place; keep only a short named span.
        import re as _re
        m = _re.search(r"\b(?:near|at|in)\s+((?:[A-Z][\w'-]+\s?){1,4})", place)
        req.place_text = m.group(1).strip() if m else None
        place = req.place_text or ""
    if hoax and not place:
        req.lat = None
        req.lng = None
        req.ward_id = None
        return
    if req.lat is not None and req.lng is not None:
        req.ward_id = ward_for_point(req.lat, req.lng)
