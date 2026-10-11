from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.models.schemas import (
    IncidentType,
    HazardType,
    UrgencyHint,
    SupportedLanguage,
    VulnerableFlags,
    FieldConfidences,
)


class RequestStatus(str, Enum):
    NEW = "new"
    NEEDS_RECHECK = "needs_recheck"
    MATCHED = "matched"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class StoredReport(BaseModel):
    id: str
    event_id: str = "event_riverbend_flood"
    pack_id: str = "flood"
    channel: str = "text"  # "text" | "voice"
    lang: str = "en"
    raw_text: str
    transcript: Optional[str] = None
    asr_confidence: Optional[float] = None
    source_id: str = "anon"
    trust_level: str = "anonymous"  # "official" | "verified_volunteer" | "registered" | "anonymous"
    request_id: Optional[str] = None
    flags: List[str] = Field(default_factory=list)
    synthetic: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StoredRequest(BaseModel):
    id: str
    event_id: str = "event_riverbend_flood"
    pack_id: str = "flood"
    type: IncidentType = IncidentType.OTHER
    place_text: Optional[str] = None
    place_cell: Optional[str] = None
    ward_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    people_count: Optional[int] = None
    vulnerable: VulnerableFlags = Field(default_factory=VulnerableFlags)
    hazard: HazardType = HazardType.UNKNOWN
    urgency_score: float = 0.0
    urgency_reason: str = ""
    status: RequestStatus = RequestStatus.NEW
    confidence: FieldConfidences = Field(default_factory=FieldConfidences)
    report_ids: List[str] = Field(default_factory=list)
    cluster_id: Optional[str] = None
    flags: List[str] = Field(default_factory=list)
    version: int = 1
    synthetic: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StoredCluster(BaseModel):
    id: str
    request_ids: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    merged_by: str = "auto_suggest"  # "auto_suggest" | "coordinator"
    undone: bool = False
    synthetic: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AuditEntry(BaseModel):
    id: str
    actor: str  # e.g. "coordinator", "intake_agent", "dedupe_agent"
    action: str  # e.g. "report_created", "status_change", "merged_cluster", "split_cluster", "weights_updated"
    target: str  # ID of target entity
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ResourceKind(str, Enum):
    BOAT = "boat"
    SHELTER = "shelter"
    FOOD = "food"
    MEDICAL = "medical"


class ResourceStatus(str, Enum):
    AVAILABLE = "available"
    DEPLETED = "depleted"
    OVERCOMMITTED = "overcommitted"
    OFFLINE = "offline"


class MatchState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class StoredResource(BaseModel):
    id: str
    event_id: str = "event_riverbend_flood"
    pack_id: str = "flood"
    kind: ResourceKind
    name: str
    landmark_id: Optional[str] = None
    ward_id: Optional[str] = None
    lat: float
    lng: float
    capacity_total: int = Field(..., ge=0)
    capacity_remaining: int
    unit: str = "people"
    status: ResourceStatus = ResourceStatus.AVAILABLE
    synthetic: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StoredMatch(BaseModel):
    id: str
    event_id: str = "event_riverbend_flood"
    pack_id: str = "flood"
    request_id: str
    resource_id: str
    score: float = 0.0
    breakdown: Dict[str, float] = Field(default_factory=dict)
    explanation: str = ""
    state: MatchState = MatchState.PROPOSED
    approved_by: Optional[str] = None
    rejected_by: Optional[str] = None
    reject_reason: Optional[str] = None
    overcommit: bool = False
    warning: Optional[str] = None
    reserved_units: int = 0
    distance_km: Optional[float] = None
    synthetic: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
