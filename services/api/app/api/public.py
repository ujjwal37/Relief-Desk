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
from app.models.firestore_models import RequestStatus, StoredReport, StoredRequest
from app.tools.storage import storage_service
from app.tools.geo import grid_cell_id

router = APIRouter(prefix="/api", tags=["Public Routes"])

# Canonical synthetic area cells for Riverbend crisis map
CANONICAL_CELLS = [
    PublicCell(
        cell_id="cell_2685_8093_w7",
        ward="Ward 7 · Riverside & Temple Rd",
        center_lat=26.8520,
        center_lng=80.9310,
        incident_counts={"rescue": 6, "food": 4, "shelter": 2},
        total_reports=12,
        severity_band="critical",
        time_bucket="Last 2 hours",
        active_hazard="Water rising, Canal Road submerged",
        alerts=["Flooded lanes · Ward 7 and Ward 4: Canal Road closed. Use Temple Road."],
        last_updated=datetime.now(timezone.utc).isoformat(),
    ),
    PublicCell(
        cell_id="cell_2686_8094_w4",
        ward="Ward 4 · North Ghat",
        center_lat=26.8610,
        center_lng=80.9420,
        incident_counts={"rescue": 4, "medical": 2},
        total_reports=6,
        severity_band="high",
        time_bucket="Last 2 hours",
        active_hazard="Waterlogging 2-3 feet",
        alerts=["North Ghat embankment warning. Rescue teams deployed."],
        last_updated=datetime.now(timezone.utc).isoformat(),
    ),
    PublicCell(
        cell_id="cell_2684_8091_w9",
        ward="Ward 9 · Mill Colony",
        center_lat=26.8430,
        center_lng=80.9180,
        incident_counts={"animal_attack": 3, "medical": 1},
        total_reports=4,
        severity_band="high",
        time_bucket="Last 2 hours",
        active_hazard="Pack of aggressive dogs spotted near Mill Colony lanes",
        alerts=["Dog attack alert · Ward 9: 3 reports in 2 h. Avoid walking alone after dark."],
        last_updated=datetime.now(timezone.utc).isoformat(),
    ),
    PublicCell(
        cell_id="cell_2687_8095_w2",
        ward="Ward 2 · Gandhi Nagar",
        center_lat=26.8720,
        center_lng=80.9520,
        incident_counts={"food": 8, "shelter": 4},
        total_reports=12,
        severity_band="medium",
        time_bucket="Last 3 hours",
        active_hazard="Drinking water shortage, community kitchen operational",
        alerts=["12 households near Gandhi High School need dry ration kits."],
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
        lat = req.lat or 26.85
        lng = req.lng or 80.93
        # Compute coarse cell id using 500m grid cell tool
        cid = grid_cell_id(lat, lng)
        # Round coordinates to coarse ~500m center grid to prevent exact geolocation leakage
        coarse_lat = round(round(lat / 0.0045) * 0.0045, 4)
        coarse_lng = round(round(lng / 0.0045) * 0.0045, 4)
        ward_label = req.ward_id or "Riverbend Central"

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
            title="Dog attack alert · Ward 9, Mill Colony",
            ward="Ward 9",
            time_ago="25 min ago",
            severity="warning",
            description="3 reports in 2 h. Avoid walking alone near the colony lanes after dark.",
            icon="dog",
        ),
        PublicAlert(
            id="alt_02",
            title="Flooded lanes · Ward 7 and Ward 4",
            ward="Ward 7 & 4",
            time_ago="1 h ago",
            severity="critical",
            description="Canal Road closed. Use Temple Road to reach the shelter.",
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
    # 1. Lookup report by ID or by token
    report: Optional[StoredReport] = storage_service.get_report(report_id)
    if not report and token:
        report = storage_service.get_report_by_status_token(token)

    # 2. Demo fallback for synthetic UI demonstration (e.g. 'R-0412', 'demo', or initial loads)
    if not report:
        if report_id in ("R-0412", "demo", "tok_demo") or (token and "demo" in token.lower()):
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
                        title="Received / प्राप्त",
                        state="done",
                        timestamp="11:42",
                        description="Request R-0412 saved in system",
                    ),
                    StatusTimelineStep(
                        step=2,
                        name="matched",
                        title="Matched / मिलान हुआ",
                        state="done",
                        timestamp="11:44",
                        description="Volunteer boat team assigned",
                    ),
                    StatusTimelineStep(
                        step=3,
                        name="on_the_way",
                        title="On the way / सहायता रवाना",
                        state="current",
                        timestamp="11:48",
                        description="Boat B-03 · from Ward 6 jetty",
                    ),
                    StatusTimelineStep(
                        step=4,
                        name="fulfilled",
                        title="Fulfilled / सहायता पहुँची",
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

    # 3. If real report found, find corresponding request
    req: Optional[StoredRequest] = None
    if report.request_id:
        req = storage_service.get_request(report.request_id)

    req_status = req.status if req else RequestStatus.NEW

    # Determine timeline states based on actual request lifecycle
    step1_state = "done"
    step2_state = "pending"
    step3_state = "pending"
    step4_state = "pending"
    hero_title = "Sent. Help is being arranged."
    delivery_status = "In progress"
    eta_display = "~20 min"

    if req_status in (RequestStatus.NEW, RequestStatus.NEEDS_RECHECK):
        step2_state = "current"
    elif req_status == RequestStatus.MATCHED:
        step2_state = "done"
        step3_state = "current"
        eta_display = "~15 min"
    elif req_status in (RequestStatus.APPROVED, RequestStatus.IN_PROGRESS):
        step2_state = "done"
        step3_state = "current"
        hero_title = "Dispatch approved. Responders on the way."
        eta_display = "~12 min"
    elif req_status in (RequestStatus.RESOLVED, RequestStatus.CLOSED):
        step2_state = "done"
        step3_state = "done"
        step4_state = "done"
        hero_title = "Assistance delivered."
        delivery_status = "Delivered"
        eta_display = "Completed"

    display_time = report.created_at[11:16] if len(report.created_at) >= 16 else "Just now"

    timeline = [
        StatusTimelineStep(
            step=1,
            name="received",
            title="Received / प्राप्त",
            state=step1_state,
            timestamp=display_time,
            description=f"Report {report.id[:8]} logged securely",
        ),
        StatusTimelineStep(
            step=2,
            name="matched",
            title="Matched / मिलान हुआ",
            state=step2_state,
            timestamp=None if step2_state == "pending" else display_time,
            description="Coordinator matching with available relief teams",
        ),
        StatusTimelineStep(
            step=3,
            name="on_the_way",
            title="On the way / सहायता रवाना",
            state=step3_state,
            timestamp=None if step3_state == "pending" else display_time,
            description="Assigned team dispatched to your area cell",
        ),
        StatusTimelineStep(
            step=4,
            name="fulfilled",
            title="Fulfilled / सहायता पहुँची",
            state=step4_state,
            timestamp=None,
            description="Confirmation requested upon rescue completion",
        ),
    ]

    return ReportStatusResponse(
        report_id=report.id,
        request_id=req.id if req else report.id,
        status=req_status.value,
        hero_title=hero_title,
        hero_subtitle=f"Report {report.id[:8]} · {display_time} · you can close the app",
        eta_minutes=15,
        eta_display=eta_display,
        delivery_status=delivery_status,
        timeline=timeline,
        while_you_wait_tips=[
            "Move to the highest safe place.",
            "Stay away from flood water and live wires.",
            "Keep your phone charged and stay reachable.",
        ],
        emergency_phone="112",
        synthetic=True,
    )
