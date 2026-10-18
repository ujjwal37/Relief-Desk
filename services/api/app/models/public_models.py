from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PublicCell(BaseModel):
    """Area-level aggregated incident cell.
    STRICT PRIVACY GUARANTEE: Never exposes individual names, phone numbers,
    exact victim coordinates, or raw report text."""
    cell_id: str
    ward: str
    center_lat: float
    center_lng: float
    incident_counts: Dict[str, int] = Field(default_factory=dict)
    total_reports: int = 0
    severity_band: str = "medium"  # "critical" | "high" | "medium" | "low"
    time_bucket: str = "Last 2 hours"
    active_hazard: Optional[str] = None
    alerts: List[str] = Field(default_factory=list)
    last_updated: str


class PublicCellsResponse(BaseModel):
    cells: List[PublicCell] = Field(default_factory=list)
    total_active_cells: int = 0
    disclaimer: str = "Area-level grid cells only. No names, phone numbers, or exact addresses are exposed."
    synthetic: bool = True


class StatusTimelineStep(BaseModel):
    step: int
    name: str  # "received" | "matched" | "on_the_way" | "fulfilled"
    title: str
    state: str  # "done" | "current" | "pending"
    timestamp: Optional[str] = None
    description: str


class ReportStatusResponse(BaseModel):
    """Status tracking for reporting public user with zero PII."""
    report_id: str
    request_id: str
    public_code: Optional[str] = None
    status: str
    hero_title: str
    hero_subtitle: str
    eta_minutes: Optional[int] = None
    eta_display: str = "~18 min"
    team_expected: bool = True
    delivery_status: str = "In progress"
    timeline: List[StatusTimelineStep]
    while_you_wait_tips: List[str] = Field(default_factory=list)
    emergency_phone: str = "112"
    analysis_status: str = "complete"
    receipt: Optional[str] = None
    place_stated: bool = True
    location_accuracy: Optional[float] = None
    location_source: Optional[str] = None
    synthetic: bool = True
    gate_outcome: Optional[str] = None
    gate_reply: Optional[str] = None
    is_case: bool = True
