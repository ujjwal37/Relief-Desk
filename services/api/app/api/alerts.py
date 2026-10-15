import re
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import CoordinatorUser, get_current_coordinator
from app.tools.anomaly import acknowledge, collect_alerts
from app.tools.storage import storage_service

router = APIRouter(prefix="/api", tags=["Alerts"])


class AlertResponse(BaseModel):
    id: str
    kind: str
    title: str
    reason: str
    ward_id: str | None = None
    severity: str
    age_label: str
    detected_at: str | None = None
    acknowledged: bool


def _with_clock(alert):
    """Turn a static 'N min ago' label into a real timestamp the client can format."""
    data = alert.model_dump() if hasattr(alert, "model_dump") else dict(alert)
    if not data.get("detected_at") and data.get("age_label") != "sample":
        match = re.search(r"(\d+)\s*min", data.get("age_label") or "")
        minutes = int(match.group(1)) if match else 0
        data["detected_at"] = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    return data


@router.get("/alerts", response_model=List[AlertResponse])
def list_alerts(coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    return [_with_clock(item) for item in collect_alerts(storage_service)]


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
def acknowledge_alert(
    alert_id: str,
    coordinator: CoordinatorUser = Depends(get_current_coordinator),
):
    acknowledge(alert_id)
    alerts = {item.id: item for item in collect_alerts(storage_service)}
    found = alerts.get(alert_id)
    if found is None:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return _with_clock(found)
