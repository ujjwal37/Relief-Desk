import hashlib
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.models.public_models import (
    PublicCell,
    PublicCellsResponse,
    ReportStatusResponse,
    StatusTimelineStep,
)
from app.agents.matching import NEARBY_KM, eta_for_distance
from app.models.firestore_models import MatchState, RequestStatus, StoredReport, StoredRequest
from app.tools.storage import storage_service
from app.tools.geo import grid_cell_id

router = APIRouter(prefix="/api", tags=["Public Routes"])


def public_code_for(report_id: str) -> str:
    """Stable short id such as RD-1042. The internal id and token stay unchanged."""
    digest = int(hashlib.sha256(report_id.encode("utf-8")).hexdigest()[:6], 16)
    return f"RD-{1000 + (digest % 9000)}"


def _format_km(km: float) -> str:
    text = f"{km:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def reporter_leg(req: Optional[StoredRequest]) -> tuple[Optional[int], str]:
    """Distance and minute quote for the team the coordinator card would show."""
    if req is None:
        return None, ""
    matches = storage_service.list_matches_for_request(req.id)
    chosen = None
    if req.assigned_resource_id:
        chosen = next((row for row in matches if row.resource_id == req.assigned_resource_id), None)
    if chosen is None:
        approved_rows = [row for row in matches if row.state == MatchState.APPROVED]
        pool = approved_rows or list(matches)
        if pool:
            chosen = max(pool, key=lambda row: row.score)
    if chosen is None:
        return None, ""
    km = chosen.breakdown.distance_km
    minutes = eta_for_distance(km)
    if km > NEARBY_KM or minutes is None or minutes > 90:
        return None, ""
    return minutes, f"{_format_km(km)} km · about {minutes} min"


# Canned status only for these ids. A token that merely contains "demo" is not enough.
DEMO_STATUS_IDS = frozenset({"R-0412", "demo", "tok_demo"})

# Canonical synthetic area cells. Places are real Kerala panchayats; the reports are not.
CANONICAL_CELLS = [
    PublicCell(
        cell_id="cell_1031_7633_w7",
        ward="Chalakudy · Thrissur",
        center_lat=10.3080,
        center_lng=76.3310,
        incident_counts={"rescue": 6, "food": 4, "shelter": 2},
        total_reports=12,
        severity_band="critical",
        time_bucket="Last 2 hours",
        active_hazard="Water rising, Temple Road submerged",
        alerts=["Flooded lanes · Chalakudy and Aluva: Temple Road closed. Use the school road."],
        last_updated=datetime.now(timezone.utc).isoformat(),
    ),
    PublicCell(
        cell_id="cell_1011_7635_w4",
        ward="Aluva · Ernakulam",
        center_lat=10.1076,
        center_lng=76.3516,
        incident_counts={"rescue": 4, "medical": 2},
        total_reports=6,
        severity_band="high",
        time_bucket="Last 2 hours",
        active_hazard="Waterlogging 2-3 feet",
        alerts=["Aluva Manappuram warning. Rescue teams deployed."],
        last_updated=datetime.now(timezone.utc).isoformat(),
    ),
    PublicCell(
        cell_id="cell_1047_7613_w9",
        ward="Anthikad · Thrissur",
        center_lat=10.4660,
        center_lng=76.1300,
        incident_counts={"animal_attack": 3, "medical": 1},
        total_reports=4,
        severity_band="high",
        time_bucket="Last 2 hours",
        active_hazard="Aggressive dogs spotted near Anthikad lanes",
        alerts=["Dog attack alert · Anthikad: 3 reports in 2 h. Avoid walking alone after dark."],
        last_updated=datetime.now(timezone.utc).isoformat(),
    ),
    PublicCell(
        cell_id="cell_0942_7641_w2",
        ward="Champakulam · Alappuzha",
        center_lat=9.4160,
        center_lng=76.4110,
        incident_counts={"food": 8, "shelter": 4},
        total_reports=12,
        severity_band="medium",
        time_bucket="Last 3 hours",
        active_hazard="Drinking water shortage, community kitchen operational",
        alerts=["12 households near Champakulam School need dry ration kits."],
        last_updated=datetime.now(timezone.utc).isoformat(),
    ),
]


class PublicAlert(BaseModel):
    id: str
    title: str
    ward: str
    time_ago: str
    severity: str  # "critical" | "warning" | "info"
    description: str
    icon: str


@router.get("/public/cells", response_model=PublicCellsResponse)
def get_public_cells(bbox: Optional[str] = Query(None, description="Bounding box minLng,minLat,maxLng,maxLat")):
    """Returns area-level aggregated cells for the public map.
    PRIVACY CONTRACT: Absolutely no names, phones, exact victim coordinates,
    or raw message text are returned."""
    # 1. Start with canonical synthetic cells for complete demo rendering
    cell_map: Dict[str, PublicCell] = {c.cell_id: c.model_copy(deep=True) for c in CANONICAL_CELLS}

    # 2. Dynamically aggregate active stored requests into coarse grid cells
    active_requests = storage_service.list_requests()
    for req in active_requests:
        lat = req.lat or 10.50
        lng = req.lng or 76.30
        # Compute coarse cell id using 500m grid cell tool
        cid = grid_cell_id(lat, lng)
        # Round coordinates to coarse ~500m center grid to prevent exact geolocation leakage
        coarse_lat = round(round(lat / 0.0045) * 0.0045, 4)
        coarse_lng = round(round(lng / 0.0045) * 0.0045, 4)
        ward_label = req.ward_id or "Kerala"

        if cid not in cell_map:
            cell_map[cid] = PublicCell(
                cell_id=cid,
                ward=ward_label,
                center_lat=coarse_lat,
                center_lng=coarse_lng,
                incident_counts={},
                total_reports=0,
                severity_band="medium",
                time_bucket="Last 2 hours",
                active_hazard=None,
                alerts=[],
                last_updated=datetime.now(timezone.utc).isoformat(),
            )

        cell = cell_map[cid]
        itype = req.type.value if hasattr(req.type, "value") else str(req.type)
        cell.incident_counts[itype] = cell.incident_counts.get(itype, 0) + 1
        cell.total_reports += 1

        if req.urgency_score >= 80:
            cell.severity_band = "critical"
        elif req.urgency_score >= 60 and cell.severity_band != "critical":
            cell.severity_band = "high"

    # Optional bounding box filter
    cells = list(cell_map.values())
    if bbox:
        try:
            parts = [float(p.strip()) for p in bbox.split(",")]
            if len(parts) == 4:
                min_lng, min_lat, max_lng, max_lat = parts
                cells = [
                    c for c in cells
                    if min_lat <= c.center_lat <= max_lat and min_lng <= c.center_lng <= max_lng
                ]
        except Exception:
            pass

    return PublicCellsResponse(
        cells=cells,
        total_active_cells=len(cells),
        disclaimer="Area-level grid cells only. No names, phone numbers, or exact addresses are exposed.",
        synthetic=True,
    )


@router.get("/public/alerts", response_model=List[PublicAlert])
def get_public_alerts():
    """Returns verified public area alerts matching docs/design/public-05-nearby.html."""
    return [
        PublicAlert(
            id="alt_01",
            title="Dog attack alert · Anthikad, Thrissur",
            ward="Ward 9",
            time_ago="25 min ago",
            severity="warning",
            description="3 reports in 2 h. Avoid walking alone near Anthikad lanes after dark.",
            icon="dog",
        ),
        PublicAlert(
            id="alt_02",
            title="Flooded lanes · Chalakudy and Aluva",
            ward="Ward 7 & 4",
            time_ago="1 h ago",
            severity="critical",
            description="Temple Road closed. Use the school road to reach the shelter.",
            icon="flood",
        ),
        PublicAlert(
            id="alt_03",
            title="Community food relief active · Ward 2",
            ward="Ward 2",
            time_ago="2 h ago",
            severity="info",
            description="12 households near you need food kits. Coordinators confirm first.",
            icon="heart",
        ),
    ]


@router.get("/reports/{report_id}/status", response_model=ReportStatusResponse)
def get_report_status(
    report_id: str,
    token: Optional[str] = Query(None, description="Status access token returned at submission time"),
):
    """Returns the multi-step status progress for a reporter without exposing any PII."""
    report: Optional[StoredReport] = storage_service.get_report(report_id)

    if not report:
        if report_id in DEMO_STATUS_IDS:
            return ReportStatusResponse(
                report_id="R-0412",
                request_id="REQ-0412",
                status="on_the_way",
                hero_title="Sent. Help is being arranged.",
                hero_subtitle="Request R-0412 · 11:42 · you can close the app",
                eta_minutes=18,
                eta_display="~18 min",
                delivery_status="In progress",
                timeline=[
                    StatusTimelineStep(
                        step=1,
                        name="received",
                        title="status.received",
                        state="done",
                        timestamp="11:42",
                        description="Request R-0412 saved in system",
                    ),
                    StatusTimelineStep(
                        step=2,
                        name="matched",
                        title="status.matched",
                        state="done",
                        timestamp="11:44",
                        description="Volunteer boat team assigned",
                    ),
                    StatusTimelineStep(
                        step=3,
                        name="on_the_way",
                        title="status.onway",
                        state="current",
                        timestamp="11:48",
                        description="Boat B-03 · from Ward 6 jetty",
                    ),
                    StatusTimelineStep(
                        step=4,
                        name="fulfilled",
                        title="status.fulfilled",
                        state="pending",
                        timestamp=None,
                        description="You can confirm when help arrives",
                    ),
                ],
                while_you_wait_tips=[
                    "Move to the highest safe place.",
                    "Stay away from flood water and live wires.",
                    "Keep your phone charged and stay reachable.",
                ],
                emergency_phone="112",
                synthetic=True,
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found. Please verify your report ID and status token.",
        )

    if not token or token != report.status_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Status token does not match this report.",
        )

    # If real report found, find corresponding request
    req: Optional[StoredRequest] = None
    if report.request_id:
        req = storage_service.get_request(report.request_id)

    req_status = req.status if req else RequestStatus.NEW
    code = public_code_for(report.id)
    approved = req_status in (
        RequestStatus.APPROVED,
        RequestStatus.IN_PROGRESS,
        RequestStatus.RESOLVED,
        RequestStatus.CLOSED,
    )
    # dispatched/completed are added later; treat the string values the same way.
    approved = approved or req_status.value in ("dispatched", "completed")
    fulfilled = req_status in (RequestStatus.RESOLVED, RequestStatus.CLOSED) or req_status.value == "completed"
    arrived = req_status == RequestStatus.IN_PROGRESS
    matched_state = "done" if approved else "pending"
    on_way_state = "done" if fulfilled or arrived else ("current" if approved else "pending")
    fulfilled_state = "done" if fulfilled else "pending"
    assigned_at = req.updated_at if req and approved else None
    eta_minutes, eta_display = reporter_leg(req) if approved and not fulfilled else (None, "")
    hero_title = (
        "status.heroDone" if fulfilled
        else "coord.resStatus.on_scene" if arrived
        else "status.heroOnWay" if approved
        else "status.heroReceived"
    )

    timeline = [
        StatusTimelineStep(
            step=1,
            name="received",
            title="status.received",
            state="done",
            timestamp=report.created_at,
            description="status.stepReceived",
        ),
        StatusTimelineStep(
            step=2,
            name="matched",
            title="status.matched",
            state=matched_state,
            timestamp=assigned_at if matched_state == "done" else None,
            description="status.stepMatchedDone" if matched_state == "done" else "status.stepMatchedWait",
        ),
        StatusTimelineStep(
            step=3,
            name="on_the_way",
            title="status.onway",
            state=on_way_state,
            timestamp=assigned_at if on_way_state != "pending" else None,
            description="coord.resStatus.on_scene" if arrived else "status.stepOnWay",
        ),
        StatusTimelineStep(
            step=4,
            name="fulfilled",
            title="status.fulfilled",
            state=fulfilled_state,
            timestamp=req.updated_at if req and fulfilled else None,
            description="status.stepFulfilled",
        ),
    ]

    return ReportStatusResponse(
        report_id=report.id,
        request_id=req.id if req else report.id,
        public_code=code,
        status=req_status.value,
        hero_title=hero_title,
        hero_subtitle=code,
        eta_minutes=eta_minutes,
        eta_display=eta_display,
        delivery_status="status.delivered" if fulfilled else ("status.onway" if approved else "status.waiting"),
        timeline=timeline,
        while_you_wait_tips=[
            "Move to the highest safe place.",
            "Stay away from flood water and live wires.",
            "Keep your phone charged and stay reachable.",
        ],
        emergency_phone="112",
        synthetic=True,
    )
