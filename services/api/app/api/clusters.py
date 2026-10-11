from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.tools.storage import storage_service
from app.models.firestore_models import StoredCluster, StoredRequest
from app.api.auth import get_current_coordinator, CoordinatorUser

router = APIRouter(prefix="/api", tags=["Requests & Clusters"])


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


@router.get("/requests", response_model=List[StoredRequest], summary="List ranked requests")
def list_requests(
    sort: str = "urgency",
    pack_id: Optional[str] = None,
    updated_since: Optional[str] = None,
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    reqs = storage_service.list_requests()
    if pack_id:
        reqs = [req for req in reqs if (req.pack_id or "flood") == pack_id]
    elif not reqs:
        storage_service.load_seed_incidents()
        reqs = storage_service.list_requests()

    if updated_since:
        # Inclusive bound so a row saved on the watermark is not skipped.
        reqs = [req for req in reqs if (req.updated_at or "") >= updated_since]

    if sort == "urgency":
        reqs = sorted(reqs, key=lambda r: r.urgency_score, reverse=True)
    return reqs


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
