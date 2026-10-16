from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt
from app.models.schemas import (
    AiCall,
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
    DISPATCHED = "dispatched"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    COMPLETED = "completed"
    CLOSED = "closed"


class StoredReport(BaseModel):
    id: str
    event_id: str = "event_kerala_flood"
    pack_id: str = "flood"
    channel: str = "text"  # "text" | "voice"
    lang: str = "en"
    raw_text: str
    transcript: Optional[str] = None
    asr_confidence: Optional[float] = None
    source_id: str = "anon"
    trust_level: str = "anonymous"  # "official" | "verified_volunteer" | "registered" | "anonymous"
    request_id: Optional[str] = None
    # The case the desk should open. A merge points at the existing case.
    case_id: Optional[str] = None
    joined_existing: bool = False
    incident_type: Optional[str] = None
    summary: Optional[str] = None
    place_text: Optional[str] = None
    ward_id: Optional[str] = None
    status_token: Optional[str] = None
    flags: List[str] = Field(default_factory=list)
    synthetic: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ReportQuote(BaseModel):
    report_id: str
    text: str
    people_span: Optional[str] = None


class PossibleDuplicate(BaseModel):
    target_id: str
    confidence: float = 0.0
    similarity: float = 0.0
    distance_km: Optional[float] = None
    minutes: Optional[float] = None
    note: str = ""


class StoredRequest(BaseModel):
    id: str
    event_id: str = "event_kerala_flood"
    pack_id: str = "flood"
    type: IncidentType = IncidentType.OTHER
    # The type the reporter picked. Tips use it until classification finishes.
    picked_type: Optional[str] = None
    # Logistics from a human-entered referral, never inferred by a model.
    required_supplies: Dict[str, PositiveInt] = Field(default_factory=dict)
    routing_note: Optional[str] = None
    place_text: Optional[str] = None
    place_cell: Optional[str] = None
    ward_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    people_count: Optional[int] = None
    # The citizen's own words for the count, such as "2-3" or "4".
    people_span: Optional[str] = None
    count_spans: List[str] = Field(default_factory=list)
    count_note: Optional[str] = None
    report_quotes: List[ReportQuote] = Field(default_factory=list)
    dedupe_trace: Optional[str] = None
    possible_duplicate: Optional[PossibleDuplicate] = None
    vulnerable: VulnerableFlags = Field(default_factory=VulnerableFlags)
    hazard: HazardType = HazardType.UNKNOWN
    urgency_score: float = 0.0
    urgency_reason: str = ""
    wait_points: Optional[float] = None
    wait_minutes: Optional[int] = None
    status: RequestStatus = RequestStatus.NEW
    confidence: FieldConfidences = Field(default_factory=FieldConfidences)
    report_ids: List[str] = Field(default_factory=list)
    cluster_id: Optional[str] = None
    merged_into: Optional[str] = None
    flags: List[str] = Field(default_factory=list)
    hoax_reason: Optional[str] = None
    raw_text: Optional[str] = None
    summary: Optional[str] = None
    ai_translation: Optional[str] = None
    ai_source: str = "offline_fallback"
    ai: Optional[AiCall] = None
    translations: Dict[str, str] = Field(default_factory=dict)
    translation_confidence: float = 1.0
    merged_count: int = 1
    analysis_status: str = "complete"
    analysis: Dict[str, Any] = Field(default_factory=dict)
    trace: List[Dict[str, Any]] = Field(default_factory=list)
    self_check: Optional[Dict[str, Any]] = None
    water_depth: Optional[Dict[str, Any]] = None
    update_count: int = 0
    assigned_resource_id: Optional[str] = None
    reserved_people: Optional[int] = None
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
    action: str  # e.g. "report_created", "status_change", "merged_cluster", "split_cluster", "weights_updated", "capacity_reserved", "capacity_released", "match_approved", "match_rejected"
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
    BUSY = "busy"
    DISPATCHED = "dispatched"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    RETURNING = "returning"
    DEPLETED = "depleted"


class LocationPoint(BaseModel):
    lat: float
    lng: float
    at: str


class StoredResource(BaseModel):
    id: str
    event_id: str = "event_kerala_flood"
    pack_id: str = "flood"
    kind: ResourceKind
    name: str
    name_hi: Optional[str] = None
    ward_id: str
    lat: float
    lng: float
    capacity_total: int
    capacity_remaining: int
    supplies: Dict[str, NonNegativeInt] = Field(default_factory=dict)
    hold_request_id: Optional[str] = None
    hold_amount: int = 0
    status: ResourceStatus = ResourceStatus.AVAILABLE
    location_updated_at: Optional[str] = None
    assigned_request_id: Optional[str] = None
    area_name: Optional[str] = None
    simulated: bool = False
    location_trail: List[LocationPoint] = Field(default_factory=list)
    sim_origin_lat: Optional[float] = None
    sim_origin_lng: Optional[float] = None
    sim_target_lat: Optional[float] = None
    sim_target_lng: Optional[float] = None
    sim_step: int = 0
    synthetic: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MatchState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class MatchBreakdown(BaseModel):
    distance_km: float
    distance_score: float  # e.g. 0-30
    capacity_fit_score: float  # e.g. 0-25
    urgency_score: float  # e.g. 0-25
    vulnerability_fit_score: float  # e.g. 0-20
    total_score: float  # 0-100 sum


class StoredMatch(BaseModel):
    id: str
    request_id: str
    resource_id: str
    score: float
    breakdown: MatchBreakdown
    explanation: Optional[str] = None
    explanation_hi: Optional[str] = None
    state: MatchState = MatchState.PROPOSED
    approved_by: Optional[str] = None
    rejected_reason: Optional[str] = None
    overcommit: bool = False
    overcommit_override: bool = False
    synthetic: bool = True
    hold_expires_at: Optional[str] = None
    hold_expired: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

