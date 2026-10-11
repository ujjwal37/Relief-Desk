from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import CoordinatorUser, get_current_coordinator
from app.config import settings
from app.tools.storage import storage_service

router = APIRouter(prefix="/api", tags=["Demo"])


@router.post("/demo/reset")
def reset_demo(coordinator: CoordinatorUser = Depends(get_current_coordinator)):
    """Reload synthetic seeds into the running API. Demo mode only. Nothing is auto-deleted in normal use."""
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo reset is only available in demo mode")
    summary = storage_service.reset_demo()
    summary["actor"] = coordinator.email
    return summary
